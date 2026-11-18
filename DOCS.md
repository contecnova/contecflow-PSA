# Contecflow PSA - Documentación

## 1. Qué es Contecflow PSA
Plataforma para gestión integral de servicios profesionales:
- Proyectos, tareas, sprints y planificación
- Tiempo, capacidad, recursos y ausencias
- Facturación, gastos, revenue y rentabilidad
- CRM, clientes, contratos y portal cliente
- Service Desk ITSM (tickets, SLA, KB, CMDB, cambios, problemas)
- BI y analítica avanzada
- IA aplicada y gobierno de IA
- Seguridad enterprise (RBAC, ABAC, GRC, SCIM)

## 2. Arquitectura
### Backend
- FastAPI
- SQLAlchemy + Alembic
- Celery + Redis para jobs y scheduler
- Pydantic Settings para configuración
- SQLite local / PostgreSQL productivo

Rutas principales:
- API v1: `/api/v1`

Entradas clave:
- `app/main.py`
- `app/worker.py`
- `app/core/config.py`
- `app/db/session.py`
- `app/api/v1/endpoints/`
- `app/services/`

### Frontend
- React + Vite
- TanStack Query + Axios
- React Router
- Componentes por dominio

Entradas clave:
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/services/api.ts` (reexporta `frontend/src/services/api/_core.ts`)
- `frontend/src/pages/`
- `frontend/src/components/`

Reglas del frontend (auditoría 2026-11, aplicadas por ESLint en error salvo indicación):
- Sin `any` explícito (`@typescript-eslint/no-explicit-any`).
- Sin `confirm`/`prompt`/`alert` nativos: `confirmar()` / `pedirTexto()` de `context/ConfirmContext.tsx` (con `palabraConfirmacion` para borrados irreversibles).
- Sin `fetch` fuera de `services/api/**` (aviso): el cliente pone CSRF y refresca la sesión; prefijos desde `services/api/urls.ts`; SSE con `apiStream()`.
- `style` solo con propiedades CSS personalizadas (`'--x': valor`) que consume una clase con `var(--x)`; lo demás, a una clase (aviso: regla local `contec/solo-variables-css-en-style`, `frontend/scripts/eslint/solo-variables-css-en-style.mjs`, registrada en `frontend/eslint.config.js`; admite por nombre los componentes de gráficos y flujos que solo aceptan `style`).
- Resets de `src/index.css` (`*{margin:0;padding:0}`, `button{color:inherit}`) en `@layer reset`: cualquier regla fuera de capa (componentes base, clases de página) les gana sin depender de especificidad ni orden de carga.
- Sin colores hex en propiedades de estilo (aviso): tokens de `index.css`. Codemods: `frontend/scripts/codemods/colores-a-tokens.mjs`, `estilos-a-clases.mjs` (clases `u-*`), `date-input.mjs`.
- Diálogos y paneles: `Modal`, `Drawer` y `useDialogo` (foco atrapado, Esc solo cierra el de arriba). Fechas: `components/ui/DateInput`.
- Gráficos: recharts; d3 solo para el grafo de fuerzas de CMDB.
- Campos: `<label htmlFor>` + `id` (con `useId`); `Input`/`Select` del kit ya lo hacen y aceptan `error`/`hint` (aria-describedby). Botones solo-icono con `aria-label`. Codemod: `etiquetas-a-controles.mjs`.
- Acento y opacidades: nunca `rgba(79,142,247,…)` ni `#rrggbbAA`; `var(--accent-border-soft|--accent-border|--accent-border-strong)` o `color-mix(in srgb, var(--token) N%, transparent)` (`alpha()` de `constants/theme`). Codemod: `acento-a-tokens.mjs`.
- Importes: `useFormatoMoneda()` (moneda de la empresa; `{ moneda }` si el dato trae la suya) o `formatearMoneda()`; sin `€`/`'EUR'` en pantallas. Excepciones: coste de IA en USD (precio del proveedor) y el portal (`MONEDA_PORTAL_POR_DEFECTO`, sin acceso a `org-defaults`).
- `manualChunks` (vite.config.js) solo nombra los vendor del arranque; páginas y librerías pesadas los trocea Rollup por `import()`.
- `aria-sort` va en la `<th>` (`ariaSort(sort, col)`), no en `SortableTH`. `zIndex` con `var(--z-*)` (codemod `zindex-a-tokens.mjs`); radios con `var(--radius-*)`.
- Sin componentes que tapen los del kit (`Modal`, `DataTable`, `EmptyState`, `KpiCard`…); cambiar el segundo factor pide reautenticación (`components/security/reautenticacion.ts`).
- Acciones que el backend puede encolar (202 `{status: 'queued'}`: informe programado, escáner de alertas, calidad de KB, envío a Jira): la pantalla dice «en curso» y refresca más tarde, no «hecho».
- Idiomas: solo `es` va en el chunk inicial; `en`/`zh` se cargan con `import()` (`i18n/appTranslations.ts`: `loadLanguage`, `diccionarioCargado`). Las claves sin traducir del castellano salen del módulo virtual `virtual:i18n-respaldo-en` (plugin en `vite.config.js`), no del inglés entero. La app no se monta hasta tener el idioma (sin parpadeo de claves). Nada de la app importa `langs/en|zh.mjs` ni `i18n/todosLosIdiomas.mjs` (solo scripts de Node).
- Respuestas del cliente: cada método nuevo de `services/api` declara `Promise<AxiosResponse<T>>` con `T` comprobado contra el serializador del backend (tipos compartidos en `services/api/tipos*.ts`, uno por dominio: `tipos-sd`, `-alm`, `-rendimiento`, `-grc`, `-finanzas`, `-bi`, `-analitica`, `-proyectos`, `-personas`, `-cambios`, `-documentos`, `-plataforma`; un nombre exportado una sola vez entre todos); sin `as unknown as` para leer `r.data`, sin `r.data?.items ?? r.data` (el interceptor ya desenvuelve) y sin interfaz local que repita la respuesta (alias del tipo compartido). `mutationFn` que llama a dos métodos con respuestas distintas: `(): Promise<unknown> =>`. Selectores de personas (asignar, mencionar, responsable): `usersApi.directory()` (`PersonaVisible`, sirve a cualquier rol), clave `['users', 'directory']`; `usersApi.list()` es `UserPublic | PersonaInterna` (el empleado no ve correo ni teléfono ajenos: `esFichaCompleta(u)`).
- Paginación en pantalla (#22): un único componente, `components/ui/Pagination.tsx` (+ `Pagination.css`, clases `pag-*`): `<Pagination page totalPages onChange total? pageSize? />`, `<nav>` con `aria-label`, `aria-current="page"` y `aria-label` por botón; con `total` y `pageSize` pinta «desde–hasta de total». El total sale de `res.meta.total` (o `X-Total-Count`); se pide `page`/`page_size` al API. Sin paginadores propios por pantalla.
- Textos del kit (`components/ui`, también `Breadcrumbs`/`PageHeader`): `useTextoUi()` (`components/ui/useTextoUi.ts`) en vez de `useAppLang()`: usa el `t` del proveedor y, montado sin `AppLangProvider` (tests, árboles sueltos), `traducirSinHook`. Claves en el módulo `uikit`.
- Controles con etiqueta visible: además de `htmlFor`/`id`, `aria-labelledby` en el control nativo (la regla `control-has-associated-label` no ve el `htmlFor`). En `.map()`: id del `useId()` del padre + clave del elemento, o un componente de fila con su `useId`. Sin etiqueta visible: `aria-label` con el texto del contexto. Cabecera de columna de acciones vacía: `<span className="u-sr-only">`; celda decorativa: `aria-hidden`.
- Estilos en línea repetidos: patrón con ≥ 15 apariciones → clase `u-*` en `index.css` + entrada en `PATRONES` de `estilos-a-clases.mjs` (`--excluir a.tsx,b.tsx` para no tocar ficheros en edición).
- Estilos en línea: se mide con `estilos-a-clases.mjs --medir` (atributos JSX `style={{…}}` en .tsx/.jsx sin tests); `grep 'style={'` cuenta también `style={variable}` y da otra cifra.
- **`style` solo con propiedades personalizadas** (pasada final de estilos): lo estático va a una clase del CSS del fichero (con `var(--token)`), lo condicional a clases modificadoras (`cond ? 'x-m1' : 'x-m2'`) y lo que es dato (porcentaje, posición, color del usuario) a `style={{ '--x': valor } as CSSProperties}` que consume la clase con `var(--x)`. En longitudes con valor numérico: `px(valor)` (`utils/estilos.ts`; React no añade `px` a las propiedades personalizadas). Objetos de Recharts (`contentStyle`, `labelStyle`, `wrapperStyle`): constantes de módulo con `var(--token)` (`constants/estilosGrafico.ts`). Lo hace `scripts/codemods/estilos-en-linea.mjs` (`--medir`, `--dry-run`, `--residuales`; idempotente); las reglas generadas van entre `/* >>> estilos-en-linea */` y `/* <<< estilos-en-linea */` al final del CSS del fichero (`Xxx.css` si ya lo importa; si no, `Xxx.estilos.css`), las modificadoras después de las base. Regla de ESLint `contec/solo-variables-css-en-style` (warn, `scripts/eslint/solo-variables-css-en-style.mjs`, opción `componentesPermitidos` para terceros que solo admiten `style`); test `__tests__/reglaEstiloSoloVariables.test.ts`.

### Reglas de capas (auditoría 2026-11)
Cada regla tiene un test que falla si se rompe.

| Regla | Cómo | Test |
|---|---|---|
| Los servicios no conocen HTTP | lanzan `ErrorDeDominio` (`app/core/errores.py`), que `main.py` traduce a la misma respuesta; devuelven datos (`core/descargas.Descarga`, `ConCabeceras`) y la API monta la respuesta (`api/descargas.py`); sin `fastapi`/`starlette` en `app/services` ni `app/db` (excepto `explicar_acceso.py`, recorre el router); `HTTPException` en `app/core`/`app/db` solo en `deps.py`, `grc_enforce.py` y `metrics.py` (dependencias y endpoint) | `tests/test_auditoria_2026_11_arquitectura_c2.py`, codemod `scripts/codemods/servicios_sin_http.py` |
| Tareas de Celery: envoltorios con su tenant | lógica en `app/services` (`trabajos_de_fondo.py`, `entrega_de_webhooks.py`, `ai_chat/agente_en_segundo_plano.py`); por organización con `en_cada_organizacion` o en `TAREAS_GLOBALES`/`TAREAS_POR_SUJETO`/`TAREAS_POR_FILA` (`app/worker.py`) con su razón; un fallo se registra con traza y se relanza | `tests/test_auditoria_2026_11_arquitectura_c2.py` |
| Un solo calendario | APScheduler replica `beat_schedule` entero (`_replicar_celery_beat`); sin `add_job` propios | `tests/test_ia_revision_2026_11.py`, `tests/test_auditoria_2026_11_arquitectura_c2.py` |
| La API no confirma transacciones | `commit()` solo en servicios | `tests/test_sin_commits_en_la_api.py` |
| Los modelos no importan servicios | invariantes de persistencia en `app/db/` (`cadena_auditoria.py`, `bloqueo_legal.py`) | `tests/test_auditoria_2026_11_capas_y_stripe.py` |
| Sin ciclos de import a nivel de módulo | métricas registradas en `app/services/metrics/_registro.py` | `tests/test_sin_ciclos_de_import.py` |
| `app/services`, `app/core` y `app/db` no importan `app.main`, `app.api` ni `app.worker` | tareas por nombre: `enviar_tarea("app.worker.<tarea>", args=...)` (`app/core/segundo_plano.py`); lo de arriba (la app FastAPI, un `get_dashboard_snapshot`) lo pasa la ruta como argumento | `tests/test_auditoria_2026_11_arquitectura_c4.py` |
| `app/core` y `app/db` no importan servicios al cargarse | dentro de la función que los usa | ídem |
| Ningún import dentro de una función esconde un ciclo (el destino ya llega al origen a nivel de módulo) | la pieza compartida baja al módulo de abajo (`presupuestos_preparar.meses_del_periodo`, `gastos_avanzados.CATEGORY_LABELS`, `service_desk/sla_del_ticket.py`) o se pasa como argumento; permitidos los cargadores de `collaboration/_bus.py` y `_storage.py` | ídem |
| Ningún `except Exception` silencioso | log con traza (`warning` si hay E/S, `debug` si no) | `tests/test_sin_except_silenciosos.py`, codemod `scripts/codemods/except_silenciosos.py` |
| Un solo emisor SMTP | `notification_service` | `tests/test_correo_un_solo_emisor.py` |
| Asignación masiva | `campos_asignables()` / `es_asignable()` (`app/core/asignacion.py`) | — |
| Trabajo lento fuera de la petición | `encolar(fn, ...)` (`app/core/segundo_plano.py`): Celery si hay `REDIS_URL`, en línea si no o con `TESTING=1`; solo funciones de `app.*` | — |
| Llamadas salientes a URLs configurables | `abrir()` (urllib) o `cliente_httpx()` (`app/core/outbound_url.py`): validan URL, cada redirección y la IP real conectada; hosts internos legítimos en `OUTBOUND_PRIVATE_HOSTS_ALLOWED` | `tests/test_auditoria_2026_11_capas_y_stripe.py` |
| Esperas, hosts y modelos de terceros desde `Settings` | `outbound_http_timeout(db, default=<la de siempre>)` (HTTP, SMTP, IMAP) / `outbound_ai_timeout` (IA, voz): el `default` del sitio vale hasta que el operador fija el ajuste (fila en vivo o `.env`); URLs: `MICROSOFT_OAUTH_BASE`, `MICROSOFT_GRAPH_BASE`, `GOOGLE_*`, `OPENAI_API_URL`, `ANTHROPIC_API_URL`, `ADOBE_SIGN_BASE_URL`; modelos: `CONTECFLOW_AI_MODEL`, `EMBEDDING_MODEL_NAME`, `OPENAI_STT_MODEL` | ídem |
| Servicios de más de 1.000 líneas | paquete con `__init__` que reexporta todo (incluidos privados) | — |

`ai_provider_service/` (9 módulos): su `__init__` propaga a los submódulos lo que se asigne al paquete (`monkeypatch.setattr(svc, ...)`), para que los parches de los tests sigan valiendo. Es un mecanismo poco habitual; si se quita, hay que apuntar los parches al submódulo.

### Revisión BPM (16-11-2026)

Recorrido de punta a punta de `/bpm` (diseño, versiones, ejecución, bandeja, permisos, i18n). Detalle de uso en README, «BPM Procesos — `/bpm`». Migración `169_bpmn_decisiones_y_codigos_de_error`. Tests: `tests/test_bpm_revision_2026_11_16.py`, `tests/test_bpm_i18n_codigos.py`, `tests/test_bpm_catalogo_traducible.py` (categorías), `frontend/src/__tests__/BpmRunPanel.test.tsx`, `frontend/src/pages/bpm/textos.test.ts`.

- **Decisiones manuales.** Una `exclusiveGateway` sin ninguna condición en sus salidas espera en la bandeja (`wait_kind = 'decision'`, rol de su calle) y quien la completa elige `flow_id`. Antes toda instancia fallaba al llegar a una: las 72 compuertas del catálogo y cualquiera dibujada en el editor (que no permite escribir condiciones) no llevan condición.
- **Lo que se ve es lo que se ejecuta.** Iniciar un proceso del catálogo sin registro lo crea con el diagrama mostrado; un registro sembrado sin editar (esqueleto lineal en castellano) recibe ese diagrama como versión nueva. Antes había que editar y guardar, y el sembrado ejecutaba el esqueleto, no lo que se veía.
- **Validación con códigos.** `GET /bpmn-processes/{id}/validation` y `validation` al guardar versión; problemas con `code` (`bpm.problema_*`). Fallo en ejecución con `error_code`/`error_params` (`bpm.error_*`). Tipos, roles y estados traducidos (`pages/bpm/textos.ts`). El XML se parsea con `defusedxml`; guardar un XML roto o que no es BPMN da 422 (antes se guardaba y el proceso ya no abría); tamaño máximo `BPMN_MAX_XML_BYTES`, variables `BPMN_MAX_VARIABLES_BYTES` (413) y nombres de variable identificadores (422).
- **Publicar.** Solo un diagrama ejecutable (422) y una sola versión publicada. Pantalla «Versiones» (ver, publicar). Archivar impide instancias nuevas (409). Antes la API existía sin pantalla.
- **Permisos.** Lecturas de `/bpmn-processes` con `require_internal_user` (antes cualquier usuario autenticado, también portal y subcontratistas). La página oculta las escrituras a team lead (la API ya le daba 403). Pestaña «Procesos» en `/inbox` para que RRHH y empleados completen sus pasos (no entran en `/bpm`). Las calles solo se asocian a roles internos.
- **Duplicar.** La copia es de la organización de quien duplica (antes heredaba la del origen: copiar uno global lo dejaba global), clave desde el nombre con `clave_unica`, conserva responsable y SLA.
- **Rendimiento y concurrencia.** El listado trae el XML en una petición (`include_xml`; antes una por proceso). `listar` y `bandeja` sin N+1 (`selectinload`/`contains_eager`). Completar y cancelar bloquean la instancia (`FOR UPDATE`): dos ramas paralelas completadas a la vez dejaban la unión sin cerrar.
- **Auditoría.** Alta, cambio, borrado, duplicado, versión, publicación, siembra, arranque y cancelación en `audit_log`.
- **Coherencia.** Las categorías de `PROCESS_CATALOGUE` son las del frontend (antes `incident`, `ai-ml`…, que no salían en la barra lateral). Un flujo que apunta a un elemento inexistente se rechaza al validar (antes 500 en ejecución).
- **Sin arreglar (motivo).** Subprocesos, eventos de borde/error/compensación, mensajes y señales: el motor los rechaza al arrancar; implementarlos es una ampliación del motor, no un arreglo. Las tareas de servicio no ejecutan nada (no hay a qué enlazarlas). El editor no tiene panel de propiedades (condiciones y temporizadores solo importando `.bpmn`). No se avisa a nadie cuando un paso llega a su bandeja. El catálogo del backend (`/seed`) sigue solo en castellano y no lo usa la página.

### Segunda auditoría 2026-11: cambios de comportamiento

- **Verificación final (15-11-2026):** el stack completo se levantó en Docker (Linux, uvicorn 0.54 con 4 procesos, nginx, PostgreSQL 16) y se recorrió con un navegador real (Playwright) en es/en/zh y tema claro/oscuro. Arreglos derivados:
  - **Capas CSS:** los resets globales (`*{padding:0}`, `button{color:inherit}`) van en `@layer reset`; lo no estratificado (componentes base con `:where`, clases de página) les gana siempre. Antes borraban el relleno y el color del botón principal de las cabeceras.
  - **Textos del armazón** (menú lateral, barra superior): la tabla `LAYOUT_TEXT` de `Layout.tsx`, solo es/en, pasa al módulo `layout_texto` de los diccionarios (es/en/zh).
  - **Chino:** 90 textos que estaban en inglés traducidos (presupuestos `pres.*`, tipos de incidencia, webhooks).

- **Pasada final de estilos en línea (`frontend/src`) y alertas del BI.**
  - *Estilos.* De 1.062 `style={{…}}` con propiedades crudas quedan 0: todos los `style` llevan solo propiedades CSS personalizadas (`'--x': valor`) o un `...style` que pasa quien llama. Por propiedad, antes: 1.441 estáticas (a), 363 condicionales (b), 149 colores/tamaños literales (c), 916 de datos (d) y 175 en objetos no resolubles. Después: (a) y (b) a clases (`-eN` base, `-mN` modificadoras; `style={S.card}`/`style={fs}` con constantes estáticas del fichero también, ~400 más que el recuento inicial no incluía), (c) a token, (d) a `'--x': valor`. Los 64 residuales de la primera tanda se cerraron así: `Input`, `Select`, `UserSelect`, `MarkdownText`, `IconButton`, `Drawer` y `PortalInput` aceptan `className` (y `Input`/`Select`/`DataTable` columnas, el del contenedor/celda; bases `ui-field`, `ui-celda-datos`, `icon-button`, `drawer drawer--<variante>`, `portal-campo`); las fábricas de estilo pasaron a clases con modificadores y variables (`S.badge(color)` → `bi-gdpr-panel-badge` + `--bi-gdpr-badge-color`; `btn(accent)` → `bi-qb-btn` + `--accent`; `PortalButton` → `portal-button--<variante>--<tamaño>`; `BadgeWithTooltip`; el campo de ticket → `campo-form`/`campo-etiqueta` globales y `useFormValidation().inputClass(base, campo)` añade `campo-form--error`); los `...style` finales se quedan como `style={style}` junto a la clase (el estilo en línea del llamador sigue ganando, como antes); iconos de color de dato → `u-dato-color` + `--dato-color`. `Cell` de Recharts va en `componentesPermitidos`. Los 4 objetos de Recharts con `tokens.*` (colores ya resueltos de `useChartTheme`) se montan en `constants/estilosGrafico.ts` (`tooltipDelTema`, `tooltipDelTemaConBorde`, `etiquetaDelTema`), junto a las constantes con `var(--token)`. Campos de formulario: `validation.inputStyle` y `getFieldErrorStyle` se eliminaron; todo campo usa `className={validation.inputClass(base, campo)}` (`campo-form` global u otra base propia; `campo-form--error` lleva doble clase para ganar a la clase del control). `FormField` usa `ui-form-field-control`/`ui-form-field-etiqueta`, `TicketDetail` `campo-form` (`AIInlineEditor` acepta `className` que sustituye su aspecto por defecto), y se retiraron `INPUT_STYLE`/`LABEL_STYLE` (`constants/theme`, `sdUtils`). Las fábricas `chip(color)`, `skBox`, `tbBtn`, `chipStyle`, `tabBtnStyle`, `tabStyle` pasaron a clases (`chip-dato` + `chipColor`, `dashkit-sk` + `medidasDeEsqueleto`, modificadores `--activo`). La regla de ESLint marca también `style={f(…)}`, salvo los ayudantes de variables CSS de su opción `funcionesDeVariables` (lista por defecto revisada a mano). Cascada: cada clase tiene la especificidad de una sola clase, no la del estilo en línea; un selector más específico que fije la misma propiedad (`.ds-card h3`) ganaría ahora, riesgo residual que no se ha podido comprobar sin ejecutar la app. Si un valor de dato es `undefined`, la propiedad cae a su valor por defecto en vez de heredar de otra regla.
  - *Tokens nuevos (literales de color sin token), en `index.css`.* Tintes/halos con `color-mix` sobre el color semántico (siguen a los 4 temas): `--success-bg-strong`, `--success-border-strong`, `--warning-bg-strong`, `--warning-border-strong`, `--danger-ring`, `--surface-hover-faint`. Velos: `--overlay-scrim`, `--overlay-scrim-soft`, `--overlay-chat`, `--overlay-chat-soft`. Sombras: `--shadow-menu`, `--shadow-drawer-lateral`, `--shadow-sidebar`, `--shadow-panel-inferior`, `--shadow-hover-soft`; texto sobre fondos oscuros: `--on-dark-text`. Velos y sombras tienen valor propio en `:root` (oscuro, heredado por freight y alto contraste) y en `[data-theme="light"]` (más ligeros, tinte pizarra). Aproximaciones declaradas: `rgba(245,158,11,.31)` pasa a 30 %, `rgba(16,185,129,.12)` y `rgba(34,197,94,.12)` al verde del tema a 12 %, `rgba(255,71,87,.18)` (halo de error) al `--danger` del tema a 18 %. Los bloques generados ya no tienen ningún hex/rgba. Tests (sin ejecutar): `reglaEstiloSoloVariables.test.ts` (RuleTester), `estilosEnLinea.test.ts` (residual 0, clases generadas existen, sin literales en bloques, tokens en `:root` y light, objetos de gráfico), `utils/estilos.test.ts`.
  - *Condiciones de alerta del BI.* `trend_down` y compañía salían como código en `SmartAlertsPanel` (selector, reglas y histórico). Ahora `etiquetaCodigo(t, 'condicion_alerta', código)` con el módulo `condicion_alerta` en es/en/zh; `SettingsPageSections` usa el mismo módulo y se retiraron sus claves `cond_*` duplicadas. Test: `i18n/__tests__/condicionAlerta.test.ts`.
  - *Planificador de recursos por ventana.* `GET /bookings` acepta `date_from`/`date_to` (tipo `date`, 422 si no lo es): solape en SQL (`end_date >= date_from` y `start_date <= date_to`; incluye las que cruzan la ventana; cada límite opcional; se combinan con `start_date`/`end_date`, que ya existían como texto). `ResourceSchedulerPage` pide solo la ventana visible (`utils/ventanaDeReservas.ts`: lunes inicial a domingo final) con clave `['bookings', desde, hasta]` y `keepPreviousData`: al cambiar el número de semanas vuelve a pedir; las mutaciones invalidan el prefijo `['bookings']`. Pruebas: `tests/test_reservas_ventana_de_fechas.py`, `utils/ventanaDeReservas.test.ts`.

- **Catálogo de procesos BPM traducido a es/en/zh y búsqueda de ALM en el servidor.**
  - *Catálogo (antes ~1.200 textos solo en castellano dentro de `BPMPage.tsx`, 61 procesos).* Ahora está en `frontend/src/pages/bpm/catalogo/`: `estructura.ts` (ids, categoría, nº de pasos, SLA en días hábiles como número, nodos y flujos del diagrama; no depende del idioma) y `textos/{es,en,zh}.ts` (nombre, descripción, responsable, SLA textual, pasos, nombre de cada nodo y etiquetas de flujo, por id de proceso y de nodo). `index.ts` los une (`construirCatalogo`) y genera el XML con `bpm/generadorBpmn.ts` (extraído de la página). Los textos se piden con `import()` por idioma, como los diccionarios principales: un usuario descarga solo su idioma (~40 KB de fuente, ~36 KB el chino) y la estructura (~43 KB de fuente) viaja con el chunk de la página. Se descartó meter ~1.200 claves en `langs/*.mjs`: habría engordado el chunk inicial del castellano y el diccionario de cada idioma con textos que solo usa una página. Medición: el chunk `BPMPage` pesaba 90,75 kB (minificado) con el catálogo dentro; el build posterior no se pudo medir porque falla por un error ajeno (`SettingsAdvancedSections.tsx:37`, `t` declarada dos veces), así que no se da cifra «después». El XML generado en castellano es idéntico byte a byte al original (comprobado contra el código anterior). Las claves nuevas del diccionario están en `bpm.sla_dia_habil`, `bpm.sla_dias_habiles` y `bpm.blank_*` (diagrama en blanco, que antes llevaba «Inicio/Actividad/Fin» en castellano). Los 20 SLA expresables como «N días hábiles» son un número y se formatean con el idioma; el resto (p. ej. «P1: 4h | P2: 8h») sigue siendo texto traducido. `catalogo.test.ts` comprueba que los tres idiomas tienen exactamente las mismas claves que la estructura (pasos, nodos, etiquetas, SLA, nombre de diagrama) y que no hay textos vacíos.
  - *Backend.* `app/services/bpmn_process_service.py::PROCESS_CATALOGUE` es **otro** catálogo (55 procesos lineales, sembrados como filas por organización con `seed_catalogue`); comparte 16 claves con el del frontend. Son datos de la organización (editables, guardados con nombre y XML), no plantillas de interfaz, y siguen en castellano. Para que los 16 solapados no pisen la traducción: un registro sembrado y sin editar (`is_seeded` y versión 1) ya no sustituye el diagrama del catálogo; en cuanto el usuario lo edita (versión 2) se respeta su XML. Los 39 restantes ya están en el catálogo del frontend como procesos lineales (ver la entrada «Procesos sembrados por el backend, traducibles» más abajo).
  - *ALM.* `GET /alm/contracts` acepta `q` (título, referencia y nombre del proveedor, sin distinguir mayúsculas; `%` y `_` cuentan como texto) y `renewal_urgent` (renueva de hoy a +`DIAS_RENOVACION_URGENTE`=60 días, la misma constante que usa el serializador para el campo `renewal_urgent`). `GET /alm/licenses` acepta `q` (nombre y proveedor) y `type`. `ContractsTab` y `LicensesTab` de `ALMPage` pagan siempre en el servidor: desaparece el modo «pedir la lista entera y filtrar en el navegador» (que además se quedaba corto en el tope del servidor). Prueba: `tests/test_alm_busqueda_servidor_2026_11.py`. Nota: el importe resumen de contratos y licencias sigue siendo el de la página mostrada cuando hay más de una.

- **Procesos sembrados por el backend, traducibles (los 39 que faltaban).** Los 39 procesos de `PROCESS_CATALOGUE` que no tenían diagrama propio en el frontend salían como «propios» con el nombre, la descripción y los pasos del backend, siempre en castellano. Ahora se añaden al catálogo del frontend con la misma arquitectura (estructura sin idioma + textos por idioma cargados con `import()`): `pages/bpm/catalogo/estructuraLineal.ts` (id, categoría de la página y nº de pasos) y `textosLineales/{es,en,zh}.ts` (nombre, descripción y un texto por paso). `cargarTextosCatalogo` devuelve además `lineales`; `construirCatalogo(textos, t, lineales)` los añade tras los de diagrama propio y `construirLineales` genera el diagrama con las mismas reglas que el backend (inicio, tareas, fin; ids `StartEvent_1`, `Activity_n`, `EndEvent_n`). Se descartó añadirlos a `estructura.ts`/`textos/*.ts`: exigen responsable y SLA, que el origen no tiene, y habría que inventarlos; así van vacíos (la página ya no pinta responsable ni SLA si no existen). Un sembrado sin editar (`is_seeded` y versión 1) muestra el texto y el diagrama traducidos del catálogo; uno editado (versión ≥ 2) conserva el XML del usuario, que es la lógica que ya tenían los 16 solapados. Nombre y descripción salen siempre del catálogo, igual que en los 16 (la página no permite renombrar). La categoría de la página es una decisión de este cambio, porque las del backend (`ai-ml`, `incident`…) no existen en los filtros de la página: Service Desk (18), proyectos (6), finanzas (2), RR. HH. (3, incluye `resource_forecast`), CRM (1) y administración (9). Tests: `catalogo/lineales.test.ts` y `tests/test_bpm_catalogo_traducible.py` (la semilla y los textos en castellano no pueden desviarse, y cada proceso sembrado debe tener textos en los tres idiomas). Fuera de alcance: `BpmRunPanel` muestra `process_name` y los pasos de las instancias en marcha, que se guardan al arrancar y son un dato de la ejecución.

- **Diccionarios sin claves duplicadas (es/en/zh).** En un literal JS la última declaración gana en silencio. Se fusionaron 13 duplicados con un script que lee el AST y conserva el valor que gana hoy (verificado: el diccionario resuelto, ignorando el orden de claves, es idéntico antes y después): 8 en `es` (`service_desk.status_in_progress`, `status_resolved`, `status_closed`, `type_change`, `type_problem`, `type_question`, `priority_p3`, `priority_p4`; estaban en líneas con varias claves y el gate anterior no las veía), 1 módulo en `en` (`semantic_engine`, declarado dos veces con las mismas claves) y 4 en `zh` (`cmdb.new_ci`, `no_cis`, `save`, `cancel`). `scripts/check_i18n_duplicates.mjs` pasa a leer el AST (antes seguía líneas y se dejaba esas 8). Test: `src/i18n/__tests__/sinClavesDuplicadas.test.ts`.

- **Frases con datos en una sola clave (59 claves nuevas, 82 sueltas retiradas).** Frases que se montaban concatenando `t()` con números en medio (`«Tienes» + n + «acciones»`) fijaban el orden del español en inglés y chino. Cada una es ahora una clave con `{variables}` en los tres idiomas (p. ej. `portaldashboard.acciones_pendientes` = «Tienes {n} acción(es) pendiente(s)»). Se corrigió de paso `bigdpr.ha`, que en inglés decía «ago» (el verbo «ha», no el tiempo). Las claves sueltas que quedaron sin uso se eliminaron (se comprobó contra todo `src`). Quedan como están, a propósito, las líneas de tipo «etiqueta: valor · etiqueta: valor» (`BIPage`, `PortalPublicViewPage`…) y las listas de mensajes independientes unidos por « · » (`TasksPage`): cada pieza ya es una unidad con su propio orden. Límite del análisis: el buscador (AST) detecta dos o más `t()` con algo en medio; una cifra pegada a un solo `t()` («{n} {unidad}») no se marca. Test: `src/i18n/__tests__/frasesConVariables.test.ts` (las 59 claves existen en los tres idiomas con las mismas variables).

- **Nombres de los catálogos del backend, traducidos por código.** El catálogo de analítica (110 métricas: etiqueta y descripción; 26 categorías) y las métricas del motor de alertas del BI (133, que también usa la previsión) llegaban en castellano. `frontend/src/i18n/catalogoMetricas.ts` los pasa por `etiquetaCodigo` con claves `catalogo_metrica.<id>`, `catalogo_metrica_descripcion.<id>`, `catalogo_categoria.<categoria>` y `catalogo_metrica_bi.<clave>` (379 por idioma), con respaldo al nombre recibido: una métrica nueva, o una propia de la empresa (`is_custom`), se ve tal cual llega. `etiquetaCodigo` quita ahora las tildes del código para formar la clave («Formación» → `formacion`). Las etiquetas del backend llevan `¤` donde va la moneda; el diccionario lo conserva y el frontend lo sustituye por el símbolo de la empresa. Usos: `ReportsPage` (selector, ficha de resultado, descripción, categorías y nombre por defecto del informe guardado), `SmartAlertsPanel` (selector, reglas, histórico y correlaciones, que mostraban el código crudo) y `BiForecastingPanel` (mostraba el id). El mapa local de categorías (`CAT_KEYS`) y sus 26 claves `reportes_ui.cat_*` se retiraron. Límite: las condiciones de las alertas (`trend_down`…) siguen mostrándose como código con guiones bajos por espacios. Tests: `src/i18n/__tests__/catalogoMetricas.test.ts` y `tests/test_catalogos_metricas_i18n.py` (cada métrica y categoría del backend está en los tres diccionarios, y el castellano del diccionario es el del backend).

- **Clave de proceso BPMN única en la base (#33, migración `168_indice_unico_procesos_bpmn`).** `clave_unica` solo comprobaba en código; dos altas simultáneas podían duplicar la clave. Ahora hay un índice único `(organization_id, key)` y otro parcial `(key) WHERE organization_id IS NULL` para el catálogo global (NULL no choca con NULL). `create_process` convierte el `IntegrityError` en `ErrorDeDominio` 409 (antes habría sido 500). La migración resuelve los duplicados previos conservando la clave de la fila más antigua y poniendo `_dup_<n>` a las demás (no borra nada; el sufijo no se revierte en el downgrade).

- **Geo-IP activado por defecto (decisión de producto, 14-11-2026):** `GEOIP_LOOKUP_ENABLED=True`. La IP pública de cada inicio de sesión y refresco se envía a `GEOIP_LOOKUP_URL` (ipapi.co por defecto) para el riesgo de sesión (cambio de país/ASN). Es una transferencia de datos personales a un tercero: requiere base legal y aviso de privacidad, salida a Internet y vigilar la cuota del proveedor. Para no enviarla: `GEOIP_LOOKUP_ENABLED=false`.

- **CSRF:** las exenciones de los webhooks de Twilio (voz) y entrada multicanal apuntaban a `/api/v1/service-desk/...`; las rutas reales son `/api/v1/sd/voice/webhook/twilio` y `/api/v1/sd/multichannel/inbound/`. Sin efecto práctico hoy (Twilio no envía cookies), pero la lista ya casa con las rutas.

- **Subcontratado con mínimo privilegio en personas y ajustes** (`app/services/politica_de_visibilidad.py`, regla única). `GET /users/{id}`: su ficha completa; de la gente de sus proyectos (PM, miembros activos, asignados de tareas), ficha mínima (id, nombre, avatar, rol, puesto); del resto, 404 (antes veía la ficha de cualquiera de la empresa menos la tarifa). `GET /users/org-chart` y la productividad ajena: 403. Nuevo `GET /users/directory` (selector de personas, ficha mínima, cualquier sesión). `/projects/{id}/team` y `/members`: el subcontratado, solo de sus proyectos (404) y sin correo ni dedicación. Menciones, búsqueda global y seguidores de ticket: solo la gente que ve y sin correo ajeno. Ajustes: cada ajuste del catálogo declara su `Audiencia` (`SESION`/`INTERNA`/`ADMIN`); el subcontratado recibe solo `SESION` en `/settings/general` y en `/settings/org-defaults` (sin `tax_rate` ni `vacation_days_per_year`). `ajustes_generales_para(db, audiencia, es_superadmin)` cambia de firma. Empleado: igual que antes, salvo dos agujeros cerrados: `GET /sd/tickets/{id}/watchers` exige ver el ticket (`scope_ticket_query`, 404 si no) y `GET /users/{id}` responde 404 (antes 403) si el id no existe. `GET /users/{id}` ya no pone `hourly_rate = None` sobre el objeto de la sesión (lo hace en la copia de respuesta).

- **Búsquedas acotadas al rol** (`cab_service/busqueda.py`). `GET /global-search` pasa cada sección por el alcance del listado de su entidad: proyectos `scope_projects_query`, tareas `build_task_list_query`, tickets `scope_ticket_query`, personas `politica_de_visibilidad`. Facturas y oportunidades solo para quien lee su módulo (`ve_modulo_financiero`: `require_any_manager` + matriz GRC `ver` no denegada) y con su alcance (`_scope_invoice_query`, `scope_opportunity_query`, solo activas). Antes un empleado o un subcontratado encontraba los de toda la empresa. Lo mismo en el asistente de IA (chat, agente y MCP): `search_all` reutiliza esas consultas (`consulta_de_*`), y `search_projects`, `get_open_tickets` y `get_pipeline` aplican el alcance o la guarda de su módulo. `GET /fts/search`: solo entradas de proyectos que se ven (y, de tareas, las del listado propio); las sin proyecto, solo para quien ve todos los proyectos. `POST /epics/nql/search`: tareas, proyectos y épicas acotadas igual. `fts_search` y `execute_nql_search` reciben el usuario.
- **Ajustes avanzados:** `GET /advanced-config/alert-configs` exige `require_admin` (como su escritura y la pestaña de la interfaz; antes, cualquier sesión). `GET /advanced-config/custom-fields/values/{id}` exige poder leer la entidad dueña según el tipo del campo (`exigir_lectura_de_valores`: proyecto, tarea, persona con ficha completa, cliente, ticket, riesgo, factura, oportunidad, contrato; otro tipo, solo admin); 404 si no. `GET /custom-fields/{project_id}/values/{task_id}` aplica `get_task_record`.
- **Miembros de proyecto:** `scope_projects_query` incluye, para empleado y subcontratado, los proyectos donde son miembro activo (`project_members`), aunque no tengan tareas ni horas.
- **Empleado con mínimo privilegio** (`politica_de_visibilidad`): `ve_contacto_ajeno` pasa a ser solo de admin, pm, team_lead y hr (antes, todos menos el subcontratado). Efectos para el empleado: `GET /users` le da su fila completa y de los demás la ficha interna (`PersonaInterna`: ficha mínima + `department`, `is_active`; sin correo, teléfono, manager ni accesos) y no busca por correo; `GET /users/org-chart` 403; `/projects/{id}/team` y `/members` solo de sus proyectos (404) y sin correo ajeno (team: ficha mínima); menciones, seguidores de ticket y búsqueda global sin correo ajeno. La interfaz ya no muestra «(undefined)» en los selectores de `DocumentsPage` y `ProjectsPage`.
- **Pipeline:** `GET /pipeline`, `/pipeline/pipeline`, `/pipeline/{id}/activities`, `/pipeline/{id}/proposal` y `/pipeline/forecast` exigen `require_any_manager`, como el resto del fichero (antes, cualquier sesión). La matriz GRC (`pipeline/ver`) ya colgaba del router.
- **Herramientas del asistente (chat, agente y MCP)** (`ai_chat/tool_execution/politica.py`). Cada herramienta declara su endpoint REST equivalente y hereda su guarda de rol y la matriz GRC (módulo y acción derivados de la ruta); sin política no se ejecuta (falla cerrada). El alcance de los datos es el de su listado: proyectos (`scope_projects_query`, vía `buscar_proyecto`/`por_proyecto_visible`), tareas (`build_task_list_query`), tickets (`scope_ticket_query`/`get_scoped_ticket_or_404`), personas (`scope_users_query` + `politica_de_visibilidad`: correo y tarifa según quien pregunta), imputaciones (`list_imputations_query`, coste ajeno oculto con `can_see_rates=false`), ausencias (`absence_service.list_absences`), alertas (`get_alerts_query`), contratos (`scope_contract_query`), facturas (`_scope_invoice_query`), aprobaciones (`scope_request_query`). Las escrituras usan el servicio del endpoint: `update_project_status` → `update_and_save_project` (admin o su PM), `create_risk` → `risk_service.create_risk`, `create_task`/`update_task` → `create_task_record`/`update_task_record` con ABAC, `update_ticket_status`/`reassign_tickets` → `apply_ticket_update` sobre tickets visibles. Cambios de rol: facturas pasan de admin/hr a `require_any_manager` (como `GET /invoices`); rentabilidad, de admin/hr a admin/pm (como `/profitability/projects`); `send_notification` y `reassign_tickets`, gestión. MCP: el endpoint sigue admitiendo a la plantilla interna, pero `tools/list` solo ofrece las herramientas que el rol puede usar y `tools/call` devuelve el motivo de la denegación.
- **Épicas y wiki por proyecto** (`epics_service.acotar_espacios`, `exigir_espacio_visible`, `exigir_pagina_visible`, `exigir_epica_visible`): para empleado y subcontratado, `GET /epics`, `/epics/roadmap`, `/epics/cfd` y `/epics/{id}` exigen ver el proyecto (404); los espacios de wiki, sus páginas, versiones, comentarios y la búsqueda, solo de proyectos que ven o de empresa (sin proyecto; al subcontratado, solo los públicos). `list_wiki_spaces` y `search_wiki_pages` reciben el usuario.
- **Git:** `GET /git/pull-requests`, `/git/pull-requests/{id}`, `/git/deployments` y `/git/tasks/{id}/pr-status` siguen a su proyecto: el empleado y el subcontratado solo ven los de sus proyectos (y no los sin proyecto) — `politica_de_visibilidad.acotar_a_proyectos_visibles`, la misma regla que la herramienta `get_git_activity`. Las funciones de `git_service` reciben el usuario.
- **Comentarios en hilo** (`GET`/`POST /epics/comments`): exigen poder leer la entidad dueña (`epics_service.exigir_lectura_de_hilo`): tarea `get_task_record`, ticket `get_scoped_ticket_or_404`, proyecto, épica y página de wiki con su regla; otro tipo, solo admin. 404 si no.
- **Plantillas de wiki:** la regla de un espacio de empresa: la plantilla interna las ve todas; el subcontratado, solo las del sistema (`acotar_plantillas`).
- **NQL:** el valor de una condición perdía las letras a, n y d (`status = done` daba `do`); ahora admite valores entre comillas (con espacios) o una palabra. `task_count` de una épica cuenta solo los vínculos activos (antes contaba también las tareas desvinculadas).
- Auditados sin cambios: `GET /conectores/contecmind/buscar` (plantilla interna; la búsqueda viaja con la identidad delegada del usuario y contecmind aplica sus permisos) y `GET /jira/search` (`require_any_manager`, credenciales Jira de la empresa).

- **Commits fuera de la API:** 9 `db.commit()` que quedaban en endpoints (cab, developer_portal, governance ×3, integrations_hub ×2, jira, predictive_observability) pasan a servicios: `audit.auditar_y_confirmar` (auditar + confirmar con rollback si falla), `jira_service.marcar_sincronizacion_completa` y `predictive_retraining_service.evaluar_y_reentrenar_organizacion_y_confirmar`. `test_sin_commits_en_la_api` vuelve a pasar.

- Contratos backend (auditoría de interfaz): `GET /sd/known-errors/{id}/tickets` resuelve el `KnownError` por su id y aplica la guarda de su problema padre (antes trataba el id como de `Problem` y daba 404 siempre).
- `GET /sd/problems` devuelve `fix_description` (la interfaz lo pisaba con "" al editar). No existe ruta de detalle de problema.
- `simulate_workflow` (aprobaciones): `candidate_count` cuenta los flujos activos cuyas condiciones encajan (antes `NameError` → 500 al encajar).
- `serialize_step` (aprobaciones) incluye `approver_department`; `VendorSerializer` incluye `tax_id`.
- `client_service` (proyectos de un cliente y disponibles) devuelve el estado como valor (`active`), no `ProjectStatus.active`; quitada la normalización de `ClientsPageTabs.tsx`.
- Wiki: `serialize_page` incluye `visibility`; nueva `PATCH /epics/wiki/pages/{id}/visibility` (admin o PM, ABAC `wiki_page`/update) que solo cambia la visibilidad; `wikiApi.portalUpdatePage` apunta a ella (antes a `/wiki/pages/{id}`, inexistente; el PATCH completo exige título y slug y reescribe el contenido).
- Barrido «nada en duro» (cierre): estados de ticket, problema, incidente mayor y tarea en tuplas
  derivadas de los enums (`ESTADOS_DE_TICKET_*`, `PRIORIDADES_DE_TICKET`, `ESTADOS_DE_PROBLEMA_RESUELTOS`,
  `ESTADOS_DE_INCIDENTE_MAYOR_RESUELTOS` en `models/service_desk/_enums.py`; `ESTADOS_DE_TAREA_TERMINADOS`
  en `models/task.py`), 46 ficheros migrados. Cambio: el panel de SLA y el wallboard cuentan como
  abiertos también los tickets `pending_third` (antes solo hasta `pending_client`). Las tuplas de tarea
  pierden un `"closed"` que una tarea no puede tener (sin efecto).
- Ventana «en riesgo» del wallboard y del panel de SLA: ajuste `SLA_AT_RISK_WINDOW_HOURS` (2 h, por
  empresa, grupo `sla`); la segunda franja del panel es el doble (antes 2 h y 4 h fijas). Mismo resultado por defecto.
- Frontend: intervalos de refresco/caché y tamaños de página en `constants/timings.ts` y
  `constants/pagination.ts` (mismos valores).
- PDF: los colores de los informes programados y del certificado de firma viven en
  `_pdf_marca` (`PALETA_DE_INFORME`, `COLOR_DE_EXITO/AVISO/PELIGRO/PAPEL`, `TINTES_DE_FIRMA`) con
  los mismos hex: no cambia el aspecto. No se unificaron con la paleta base porque sus grises y su
  azul difieren (`#1e293b`/`#64748b`/`#4f8ef7` frente a `#1a1a2e`/`#6b7280`/`#00d4ff`).
- `NOMBRE_DEL_PRODUCTO` sale de `settings.PROJECT_NAME` (antes el literal "Contecflow"); lo usan
  también los prompts de IA y los textos de Slack/Teams. La marca de la empresa sigue mandando donde
  ya mandaba. `/contecflow` (comando de barra) no cambia.
- Ajustes nuevos con el valor de siempre: `SD_AUTO_CLOSE_HOURS_AFTER_RESOLUTION` (72) y
  `SD_VALIDATION_WINDOW_HOURS` (48) como base de la config de autorresolución de cada empresa;
  `KEDB_DEFAULT_REVIEW_DAYS` (90, por empresa; la petición puede omitir `review_days`/`extend_days`);
  `DEFAULT_PRODUCTIVE_HOURS_YEAR` (1700) y `DEFAULT_EMPLOYER_COST_PCT` (0.32), por empresa (perfiles,
  presets y simulación de coste los usan cuando no se envían); `ORG_DEFAULT_MAX_USERS` (25) y
  `ORG_DEFAULT_MAX_PROJECTS` (100), de plataforma.
- Frontend: zona por defecto = la de la empresa (`/settings/org-defaults`) y, mientras carga, la del
  navegador (antes 'Europe/Madrid'); los selectores ofrecen todas las zonas IANA
  (`constants/timezones.ts`, antes tres listas cortas distintas). El idioma por defecto del agente de
  voz es el de la empresa. La cabecera muestra el `app_name` de la marca de la empresa
  (`useAppName`); el resto de textos de marca usan `constants/brand.ts`. `targetNamespace` BPMN:
  `http://contecflow/bpmn` en los dos lados (el frontend escribía `http://contecflow.io/bpmn`; no
  había diagramas guardados en la base local para comprobar más; la etiqueta no afecta a la lectura).
- **SSO:** el alta solo admite la organización de quien la crea (antes, cualquiera: toma de cuentas en otra empresa). El superadmin nunca entra por SSO. Si la cuenta ya está ligada a un `sub`, otro `sub` con el mismo email se rechaza (patrón nOAuth).
- **Correlación de alertas:** el job programado recorre empresa a empresa; nunca agrupa tickets de varias.
- **Webhooks salientes:** solo los de la organización del evento; un evento sin organización no se entrega.
- **Catálogos (estados y tipos de proyecto, estados de tarea):** las filas globales solo las cambia el superadmin (403 para el resto); las altas son de la empresa de quien las crea.
- **Nodo `http_call` de workflows:** URL validada y conexión por `cliente_httpx` (SSRF).
- **Bloqueo de login:** `LOGIN_MAX_ATTEMPTS`, `LOGIN_ATTEMPT_WINDOW_SECONDS` y `LOGIN_LOCKOUT_SECONDS` se leen del ajuste en caliente (caché de 60 s); antes solo del `.env`.
- **Tipos de cambio:** nueva tarea `actualizar-tipos-de-cambio` (16:30) que descarga los del BCE si `EXCHANGE_RATES_AUTO_UPDATE` está activo.
- **Autorresolución manual:** usa `SD_AUTONOMY_RESOLVE_THRESHOLD` de la organización (0,80 por defecto) en lugar de 0,65 fijo; se puede forzar.
- **Errores del frontend:** `POST /api/v1/client-errors` (público, solo log, 30/min). Antes iban a una ruta inexistente.
Tests: `tests/test_auditoria_2026_11_segunda.py`.
- **Webhook de Jira (#14):** secreto por organización (`POST /api/v1/jira/webhook-secret`, admin; se muestra una vez; Jira lo envía en `X-Atlassian-Webhook-Token` o firma el cuerpo en `X-Hub-Signature-256`; `?org=` opcional solo acota). `JIRA_WEBHOOK_SECRET` global ya no autentica. El evento solo toca tareas/tickets de esa organización. La sincronización periódica va organización por organización con su configuración (la global ya no se sincroniza) y solo actualiza tareas ya enlazadas.
- **Jira legado (#25):** `jira_url` validada al guardar y en cada petición (`cliente_httpx`); los errores no repiten la respuesta remota.
- **Microsoft 365 (#15):** `user_upn` (calendario, eventos, hitos) debe ser el email de un usuario activo de la organización (403); la presencia omite el resto. `teams/notify`: `webhook_url` HTTPS validada (SSRF).
- **MFA (#21):** `POST /auth/mfa/setup` con 2FA activo y `POST /auth/mfa/webauthn/register/start` piden `{"password"}` o `{"code"}` TOTP (401 sin ellos). El frontend debe enviarlos.
- **MFA, un solo sistema:** fuera `/api/v1/mfa/*` (`status`, `setup`, `verify`, `validate`, `disable`), `mfa_service.py` y la tabla `mfa_configs`, que el login no miraba. La pantalla /mfa usa `/auth/mfa/*`: nuevo `GET /auth/mfa/status` (`enabled`, `passkeys`, `reauth_required`, `verified_at`, `backup_codes_remaining`); `verify-setup` devuelve 8 `backup_codes` (`mfa_backup_codes.user_id`, se rehacen en cada alta; `setup` y `disable` los borran); `disable` es `POST`. Con una passkey, el alta de TOTP pide contraseña o código (la pantalla lo pide). Migración `160_mfa_un_solo_sistema`: quien lo activó solo en la pantalla pasa a tener el mismo secreto en `users.mfa_secret` y **desde ese momento el login le pide el código**; conserva sus códigos de respaldo sin usar; quien ya tenía TOTP en `users` no cambia. Añade `users.mfa_verified_at`. Irreversible. `mfa_coverage` del informe de cumplimiento cuenta `users.mfa_enabled`+`mfa_secret` y passkeys activas (antes `mfa_configs` y passkeys borradas). La supresión RGPD borra el secreto TOTP.
Tests: `tests/test_mfa_un_solo_sistema.py`.
- **Sesiones (#22):** cookie `refresh_token` con `Path=/api/v1/auth` (antes `/api/v1/auth/refresh`, que se borra). Logout y cambio de empresa revocan el refresco; cambiar la contraseña revoca las demás sesiones; restablecerla, todas.
- **Portal (#23):** el token lleva `jti` y el logout lo revoca hasta su caducidad (Redis o memoria); contacto desactivado fuera en cada petición.
- **Webhooks de colaboración (#24):** `secret_token` completo solo para admin/superadmin; el resto, `••••` + 4 últimos.
- **OAuth (#26):** DocuSign/Adobe Sign con `state` firmado, de un uso, ligado al admin y su organización (callback sin él: 400). Integraciones de colaboración: mismo `state` (ya no en memoria del proceso) + cookie `collab_oauth_bind` del navegador que inició el flujo; los tokens solo se guardan en una integración de esa organización.
- **Constructor de informes (#27):** `users.hourly_rate` e `imputations.hourly_rate_snapshot` vacíos salvo admin/RR. HH. (la propia sí); `cost_amount` vacío en imputaciones ajenas de proyectos con `can_see_rates = false`. Filtrar por ellas sin verlas: 403; ordenar se ignora.
- **PDF (#28):** texto del usuario escapado antes de `Paragraph`; `primary_color` solo `#RRGGBB`; nombre de fichero saneado.
- **Avisos de aprobación (#29):** `notify_event` exige organización (la de la aprobación o la de la sesión) y solo usa sus Slack/Teams; los aprobadores por rol/departamento son de la organización de la solicitud.
- **Correo entrante (#32):** sin organización resuelta no se busca ticket ni se reconoce contacto (ticket nuevo de externo); el contacto se reconoce solo en la organización. Si la `Authentication-Results` superior no da SPF/DKIM/DMARC `pass` alineado con el `From`, el correo es de un externo: comenta sin actuar como agente/contacto y sin cambiar estado.
- **Login (#45):** usuario inexistente también hace un bcrypt (sin oráculo por tiempo); contador por cuenta (todas las IP) con umbral 3× `LOGIN_MAX_ATTEMPTS`; el SSO aplica `require_mfa` de la organización de la sesión (403 sin factor).
Tests: `tests/test_auditoria_2026_11_seguridad_2.py`.
- **Configuración (#16):** 95 lecturas de entorno en 36 ficheros pasan a `Settings` (`config_groups/proceso_config.py`, mismo nombre y defecto); quedan 5 (`TESTING`, `PYTEST_CURRENT_TEST`, `PROMETHEUS_MULTIPROC_DIR` ×2, `DATABASE_URL` del CLI `migrate_to_pg`) y un test falla con cualquier otra. Los booleanos aceptan `1/true/yes/on` (antes solo `1`; `TENANT_AUTO_*=true` antes los **apagaba**) y vacío = defecto. Un valor en `.env` ya cuenta aunque no se exporte al proceso. **No arranca** con `DISABLE_CSRF_MIDDLEWARE=1` en staging/producción; `TENANT_AUTO_*=0` allí deja CRITICAL. La clave de OpenAI recuperada de la base ya no se escribe en `os.environ`.
- **Escalas (#17):** `app/core/escalas.py`. Probabilidad predicha → nivel con `RISK_PROBABILITY_*` (0,75/0,50/0,25, en vivo, grupo `risk`): `ml_trainer` pasa de 0,70/0,50/0,30 (0,70–0,75 baja a high; 0,25–0,30 sube a medium); avisos del oráculo de `>0,75`/`>0,5` a `≥`; `bi_intelligence` de 0,7/0,4 sin «medium» a la escala común (aparece «medium» en 0,25–0,50). Correlación de alertas → acción con `ALERT_CORRELATION_*` (0,65/0,35, en vivo, grupo `service_desk`): la pasada estructural usaba 0,70/0,40 (afecta a `GET …/service-desk/alerts/correlate` de `misc.py` y a `get_correlation_stats`, que no enriquecen; los demás caminos ya usaban 0,65/0,35). Simulación de despliegue de cambios y probabilidad de baja de clientes conservan su escala (con nombre).
- **Geo-IP (#30):** `GEOIP_LOOKUP_ENABLED=0` por defecto: ya no se envía la IP de cada login/refresco a ipapi.co (país/ASN solo de cabeceras `cf-ipcountry`/`x-asn` del proxy). Activado: `GEOIP_LOOKUP_URL`, caché por IP (`GEOIP_CACHE_TTL_SECONDS`, 1 día; fallos 5 min), solo IPs públicas, `cliente_httpx` con `OUTBOUND_HTTP_TIMEOUT_SECONDS` (10 s; antes 1,5 s fijos). Sin él, «Cambio de país/ASN» del riesgo de sesión solo salta con esas cabeceras.
Tests: `tests/test_auditoria_2026_11_config_2.py`.
- **Capas y ciclos (#43):** 7 imports de `app.main`/`app.api`/`app.worker` desde servicios y core → 0 (`enviar_tarea` por nombre de Celery; `grc_service.ensure_matrix_covers_all_modules(db, matriz, request.app)`; `APAGADOS_SIN_CONFIGURAR` en `governance_service`); 3 imports de servicios al cargar `app/core` → 0; 10 imports en función que cerraban un ciclo → 3 (cargadores de `collaboration`). `bi_embed_service.pagina` recibe `get_dashboard_snapshot`; `presupuestos_preparar.copiar_de_otro` recibe `real_mensual`. Sin cambio funcional.
- **Esperas y hosts (#38):** `timeout=<número>` 65 en 32 ficheros → 15 (subprocesos locales, sondeo de Redis, SNMP, y `worker`/Jira/Slack fuera de alcance). Cada sitio conserva su espera mientras `OUTBOUND_HTTP_TIMEOUT_SECONDS`/`OUTBOUND_AI_TIMEOUT_SECONDS` no se fijen; fijados, mandan en todos (SMTP e IMAP incluidos). **Cambio:** los 4 sitios que ya pasaban `default=15` (pruebas de integración M365, tipos de cambio ×2, Jira) esperaban 10 s por un fallo del helper y ahora 15 s. Hosts fuera de `Settings` 26 → 0 y modelos 12 → 0 (queda uno en un docstring). Nuevos: `MICROSOFT_GRAPH_BASE` (también da el `scope` `<base>/.default`; nubes soberanas) y `EMBEDDING_MODEL_NAME`; `chat.model_used` toma `CONTECFLOW_AI_MODEL` por defecto.
Tests: `tests/test_auditoria_2026_11_arquitectura_c4.py`.
- **Jira en una capa (#34):** `services/jira_service.py` es la única: cliente (`cliente_jira`/`llamar_a_jira`), mapas (`JIRA_STATUS_MAP`… y los del ticket), prueba (`probar_conexion`); `/jira/*`, `/integrations/jira/*`, `/integrations-hub/jira/*`, `jira_sync_service` y el worker delegan. Configuración única `sd_jira_configs`: la de tareas es la fila `usar_para_tareas` (una por organización; `POST /jira/config` la crea/actualiza; visible y editable en `/integrations/jira/configs`, campo nuevo `usar_para_tareas`). Migración `159_jira_una_sola_configuracion` copia las cuatro `app_settings` `jira_*` y las borra (las globales solo si hay una organización); `jira_webhook_secret` sigue en `app_settings`. Sin fallback global. La sincronización periódica ya no devuelve a `todo`/`medium` un estado/prioridad que no conoce (lo deja); `Blocked` → `blocked` en todos los caminos. `/integrations/jira/configs/{id}/test` con error: `"Jira devolvió HTTP 401"` (antes `"HTTP 401"`). El hub (`integrations-hub/jira/*`) ya no devuelve el cuerpo remoto.
- **Entrega de informes (#35):** `services/entrega_saliente.py`: `enviar_a_webhook` (Slack/Teams/API de Slack; URL validada + `cliente_httpx`), `enviar_informe_por_correo` (`notification_service`, un mensaje por destinatario). Lo usan `integrations.send_slack_message`/`send_teams_message`, `slack_service`, `POST /notifications/slack/block-kit` (URL interna del cuerpo: 400; antes `httpx` sin validar), `scheduled_reports` y `bi_report_delivery_service` (antes `httpx.post` sin validar). Los dos sistemas programados siguen separados (tabla `scheduled_reports`: informe tipado KPI/métrica en PDF de `report_pdf_service`; `bi.delivery.schedules`: preset del constructor BI exportado como datos con «solo si cambia»). `scheduled_reports` ya no exige `SMTP_USER` y manda un correo por destinatario (antes todos en `To`). PDF del envío BI = `report_pdf.generate_report_pdf` (marca de la organización, 100 filas + nota; antes ReportLab propio, 500 filas). BI valida `slack_webhook_url`/`teams_webhook_url` al guardar (400).
Tests: `tests/test_auditoria_2026_11_arquitectura_c3.py`.
- **Código muerto (#40/#45).** Regla para rutas: se borra solo si (a) no está documentada como API pública, (b) no la llama `frontend/src` ni tests/scripts y (c) su servicio no lo usa otro código vivo o duplica otra ruta. Se quedan las externas por diseño (webhooks, SAML, SCIM, tus, `bi/data`, `bi/tokens`, `bi/embed`, conectores contec*), alias de compatibilidad (`/raci/*`, `/governance/prompts`), las que comparten servicio con worker u otras rutas, lecturas de auditoría (`/sd/autonomous/log|stats`) y `/pdf/*` (endurecida en #28). Borradas 27 rutas: módulos `sd/capacity` (6), `sd/reports` (5), `marketplace` (6, fachada), `onboarding.py` (3, stub; el real es `/onboarding` de `cab.py`), `collaborative` (1, 501) y `GET /sd/stats`, `/sd/predictive/at-risk`, `/sd/known-errors/stats`, `/slack/logs`, `/bi/versioning/temporal`, `/cmdb/wiki-export/jobs`, con sus servicios (`capacity_planning_service`, `sd_reporting_service`, `stats_service` y las funciones que solo usaban). Símbolos: def/clase top-level cuyo nombre no aparece como token en `app/`, scripts ni alembic se borra (con su test si solo probaba eso); se quedan modelos con tabla (`ALMRenewalAlert`), lo de Jira (otro frente) y los de tests que son oráculo o hueco funcional (`comprobar_firma`, `tipos_soportados`, `generate_scim_token`, `record_self_approval_violation_for_request`). Módulos sin import borrados: `core/abac.py`, `endpoints/projects/projects.py`, `endpoints/admin/`. Dependencias sin import ni dependiente obligatorio: `passlib`, `aiofiles`, `pyarrow`, `trio` (+ `outcome`); `reportlab` solo en `requirements.txt`.

- **Bucle de eventos (#12):** medidos 49 endpoints `async`, 14 bloqueaban (BD/red síncrona en el bucle); ahora 46 y 0. `transcribe-chunk` y las dos subidas de adjuntos pasan a `def`; WebSockets (notificaciones, portal, documentos, colaboración), webhooks de Git, Teams (`urlopen`/JWKS) y TUS `DELETE` usan `run_db`. En los WebSocket, sondeo y mensajes de una conexión van en fila (cerrojo) para no compartir la sesión entre hilos. Guarda AST en el test.
- **`encolar` (#20):** encola `_ejecutar_con_contexto(ruta, org, args, kwargs)` (firma del worker sin cambios). Empresa: `_organizacion=` o la de `_sesion.info`. Si la función tiene `db`, el worker abre `worker_db_session` con `organization_id`/`is_superadmin=False`; en línea usa la sesión pasada. Devuelve `EN_COLA` o el resultado en línea; `respuesta_en_cola()` = 202 `{"data": {"ok": true, "status": "queued", …}}`.
- **Trabajo sacado de la petición (#20):** con broker responden 202 `status: "queued"` (sin broker, igual que antes): `scheduled-reports/{id}/run` (+`report_id`, `recipients`; resultado en `last_status`), `bi/intelligence/delivery/run/{id}`, `bi/delivery/schedules/{id}/send-now` (resultado en el log de entregas), `cmdb/discovery/run-all` y `run-due` (`results: []`), `alert-clusters/run-scan`, `kb/quality/run`, `currency/sync-ecb` (fallo del BCE ya no es 502), `jira/push` (`dry_run` sigue síncrono), `integrations/salesforce/sync-opportunities` (validación 404/400/503 en la petición; credenciales no viajan por la cola), `bookings/workflows/process-queue`, `collaboration/admin/email-digest/run` (`dry_run` síncrono). `password/forgot` encola el correo; respuesta igual (y sin oráculo de tiempo). Se quedan síncronos: `currency/sync-openexchangerates` (llevaría el `app_id` a la cola) y `jira/sync` (la UI pinta los contadores).
- **Jira (#31):** `jira-integration/sync/{id}` ya no pasa la sesión de la petición a `BackgroundTasks`: encola `run_incremental_sync(config_id=…)` en la empresa de la configuración, con sesión propia.
Tests: `tests/test_auditoria_2026_11_arquitectura_c1.py`.
- **Tareas por organización (#33):** de 45 tareas, 28 corren una vez por organización activa con su sesión y su contexto (`como_organizacion`): lo que leen es de esa organización y lo que crean queda en ella. Antes 36 leían todas y creaban con `organization_id` NULL. **Cambios:** `compliance_check` guarda un informe por organización (antes uno global invisible); `run_scheduled_reports`, `bi_kpi_push`, `bi_ml_retrain`, `ml_model_retrain`, `aplicar_retencion`, `revenue_monthly_recognition`, `predictive_model_eval_retrain` y `alert_correlation_scan` recorren las organizaciones **activas** (antes también inactivas o las que tuvieran filas). `call_ai` recibe la organización en la RCA automática (`problem_service`) y el asistente RCA (tope de gasto, proveedor y gobernanza de esa organización). Globales (6): rotación de claves, ETL OLAP, reparto de conectores ETL, purga de empresas, tipos del BCE, purga del registro de conectores. Por sujeto (4) y por fila (7): con su razón en `app/worker.py`.
- **Worker como envoltorio (#37):** `app/worker.py` 1.666 → 700 líneas; accesos a BD 22 → 0, commits 16 → 0; ninguna tarea > 30 líneas. **Cambio:** las 17 tareas que devolvían `{"error": …}` ahora fallan (FAILURE, traza con `exc_info`); un fallo de una organización no para a las demás y sale al final como `FalloEnOrganizaciones` (causa = el original). Facturas de retainer, problemas recurrentes y puntuación de cambios confirman elemento a elemento y lanzan `FalloParcial` si alguno falla. `run_agent_task` con ejecución o usuario inexistente falla (antes SUCCESS); un bloqueo de gobernanza devuelve `{"ok": false, "bloqueado": …}`. `scheduled_reports.run_due_reports` ya no se traga los errores (borrada después, #19); el informe de cumplimiento que no se guarda propaga el error.
- **Calendario (#45, worker):** `catalog_popularity_update` eliminada (no hay columna donde guardar; `updated` siempre 0 y nadie leía el resultado; la popularidad se calcula al pedirla). APScheduler ya no tiene los 7 `add_job` propios ni `automation_jobs.py`: replica `beat_schedule` entero y al arrancar (en pausa) quita del job store persistente los ids viejos (`scheduled_reports`, `scheduled_key_rotation`, `scheduled_alert_engine`, `scheduled_perf_reminders`, `automations_events`, `automations_scan`, `bpmn_timers`).
- **HTTP fuera de servicios (#36):** importes de `fastapi`/`starlette` en `app/services`+`app/db` 27 → 1 (`explicar_acceso.py`); `raise HTTPException` en `app/core`+`app/db` 44 → 12, todos en dependencias (`deps.py`, `grc_enforce.py`, `metrics.py`); `except (HTTPException, ErrorDeDominio)` en servicios 11 → 0. La dependencia del portal (`get_current_portal_client`) pasa a `core/deps.py`; descargas como `Descarga` (API: `api/descargas.respuesta_de_descarga`). Misma respuesta HTTP (status, detail, cabeceras); desde el worker, `exigir_organizacion_activa` lanza `ErrorDeDominio(403)`.
Tests: `tests/test_auditoria_2026_11_arquitectura_c2.py`.
- **WebSockets (#7):** el ticket de `GET /ws/ticket` guarda la organización ACTIVA de la sesión; al abrir (notificaciones, documentos, chat, BI) se publica esa, revalidando la pertenencia (sin ella, la de ficha; el chat corta con 4403 si se retira a mitad). `bi/collaboration/.../updates` usa el claim `org`. Tickets viejos sin organización: la de ficha.
- **Bots Slack/Teams (#8):** `SLACK_TEAM_ID`/`TEAMS_TENANT_ID` vinculado a más de una organización → rechazo (Slack 403; Teams «no encuentro usuario»), sin búsqueda global. Sin vínculo, como antes. Firma de Slack con el secreto de la organización del `team_id` (credencial `slack.signing_secret` o ajuste `SLACK_SIGNING_SECRET` de esa organización), si no el global.
- **Twilio (#9):** SMS entrante verificado con el token de la organización del número `To` (credencial `twilio.auth_token` o ajuste `TWILIO_AUTH_TOKEN` de la organización), si no el global. Voz: mono-organización por diseño (token global, sesión sin organización).
- **Organización desactivada (#10):** 403 en `/sd/events/{source}`, webhook entrante de colaboración, check-in de agente CMDB, `/portal/view/{token}` y enlaces de aprobación por correo (la de la solicitud). Trabajos de fondo: eventos de ticket (se dan por tratados sin avisos), automatizaciones (`status = skipped`), BPMN y esperas de workflow (se saltan; siguen pendientes) — `entrada_service.organizacion_desactivada`.
- **#11:** `/auth/sso/providers` en `email_selector` exige `email` o `domain` y solo devuelve proveedores con ese dominio en `allowed_domains` (o globales sin dominios); sin parámetro, `[]`. El login los pide al escribir el correo. `sem_profiles` único por (`user_id`, `organization_id`) — migración `162_perfil_semantico_por_organizacion` (rellena la organización con la de ficha). `POST /analytics/olap/refresh`: solo superadmin.
- **#19:** borradas sin llamadas `alert_service.run_alert_engine_job`, `perf_reminder_service.run_perf_reminders_job`, `resumen_de_avisos.enviar_job`, `retencion.aplicar_job`, `scheduled_reports.run_due_reports` (sesión propia sin contexto de tenant); el worker usa las funciones por organización.
Tests: `tests/test_pendientes_multitenant_2026_11c.py`.
- **SoD, autoaprobación (#1):** 403 «SoD» (`exigir_que_no_sea_suyo`, un solo registrador `grc_sod`) también en `POST /budgets/{id}/decision` (quien creó el presupuesto; la bandeja ya lo impedía), `POST /sd/tickets/{id}/approval` (quien pidió el servicio, admin incluido) y `POST /sd/changes/rollout-plans/{id}/approve` (quien creó el plan). Reglas por defecto nuevas `budgets` y `sd` (crear ⟂ aprobar); `catalog_request`/`rollout_plan` → módulo `sd`.
- **Reglas SoD (#2):** `DEFAULT_SOD_RULES` vive en `grc_sod` (reexportado en `endpoints/grc.py`). Se siembran al crear la empresa (`create_organization`) y, en las que ya existían, en la primera comprobación de autoaprobación (sin commit propio). Siguen sembrándose solo si la empresa no tiene ninguna: una empresa con reglas no recibe las dos nuevas sola.
- **Matriz del subcontratado (#3):** por defecto `False` en todas las acciones de `budgets, invoices, revenue-recognition, accounting, user-costs, rate-cards, profitability, organizations, grc, gdpr`; en `settings` se quitan `crear/editar/eliminar` y en `users` `crear/eliminar`; en los dos, `aprobar/exportar` también en `False` (ninguna ruta de esos módulos las usa) y las seis acciones quedan declaradas (la interfaz lee traducciones, estados y `/users/me/preferences` y edita `PATCH /users/me`). `sd`/`absences` intactos. Solo afecta a casillas globales sembradas de nuevo (instalación nueva o «Resetear matriz» del superadmin).
- **Supresión RGPD (#4):** `audit_logs` sigue fuera a propósito (art. 17.3.b/e; la cadena). Nuevo: con un bloqueo legal activo en sus empresas cuyo valor es el id, correo o usuario de la persona, 409 con los casos y no se reescribe nada (`supresion_service.exigir_sin_bloqueo_legal`; también antes de tocar tickets en `bi_gdpr_service.execute_erasure` y antes de marcar «en curso» en `cab_service.process_gdpr_request`).
- **Informe de cumplimiento (#5):** controles nuevos `session_revocation` (cambio/restablecimiento de contraseña revocan refrescos: `revocar_sesiones_del_usuario`; cuenta las sesiones revocadas por eso) y `sso_policy` (SSO configurado, `require_mfa`, `allowed_domains`; `attention` si un proveedor activo da de alta usuarios sin dominios; `info` sin SSO). Firma igual.
- **Retención y bloqueo legal (#6):** tipos nuevos `connector_calls` (`conector_llamadas`, `created_at`; `id, user_id, producto`), `webhook_deliveries` (`created_at`; `id, webhook_id, event`), `email_logs` (`sent_at` o `created_at`; `id, to_address, source, source_id`) y `activity_events` (`created_at`; `id, actor_id, entity_type, entity_id, target_id`). No hay modelo de «activity log» aparte de `activity_events`.
- **Auditoría sin commit (#20):** barrido AST de `app/api`+`app/services` (auditoría tras el último commit de la función): 11 marcadas, 4 reales → 0 (`governance` `PATCH ai-modules`, `organizations_service.assign_user_to_org`/`remove_user_from_org`, `subcontratas.create_sub_invoice`). Las 7 restantes son falsos positivos verificados (la llamada siguiente confirma: `grc_service.*_db`, `ABACService.audit_access_decision`, login/cambio de empresa/restablecimiento).
- **Lecturas GRC por empresa (#21):** `list_violations_db`, `get_violation_or_404`, `get_sod_rule_or_404` y `list_audit_log_db` filtran por `organization_id` explícito (antes, solo el filtro de tenant: el superadmin veía todas las empresas).
Tests: `tests/test_pendientes_grc_2026_11c.py`.
- **Entregas de webhooks (#22):** `GET /enterprise/webhooks/deliveries` (admin): entregas de todos los webhooks salientes de la empresa en una consulta, paginado (`page`, `page_size`), filtros `webhook_id`, `event`, `success`; cada fila trae `webhook_name`/`webhook_url`. `/enterprise/webhooks/{id}/deliveries` sigue. La pantalla Webhooks (log) usa el nuevo y ahora muestra las entregas **salientes** (antes pedía, una vez por disparador, los logs de los webhooks *entrantes* de CAB con otros campos).
- **Jira del hub (#23):** `/integrations-hub/jira/*` usa la `JiraConfig` de tareas de la organización (`usar_para_tareas`): nuevos `GET|PUT|DELETE /integrations-hub/jira/config` (PUT/DELETE admin; sin `api_token` se conserva el guardado; DELETE desactiva y borra el token) y `POST /integrations-hub/jira/sync`. `issues`/`search`/`transition` ignoran `integration_id`; `test` sin cuerpo prueba la guardada. `POST /oauth-integrations` con tipo `jira` escribe en la `JiraConfig`; el listado ya no devuelve Jira. Migración `161_jira_hub_a_jira_config`: copia las filas `integration_configs` de tipo jira (si la organización no tenía conexión; gana la existente) y las desactiva sin token ni JSON. Empresa → Integraciones: mismo formulario (+ clave de proyecto); el token ya no viaja al navegador.
- **Cambio de empresa (#26):** `switch-organization` a una empresa de la que se es miembro por pertenencia daba 401 (el filtro de tenant de la sesión ocultaba la pertenencia); `organizaciones_del_usuario` la lee sin filtro.
- **Tests aislados (#27a):** el encoder TF-IDF de los tests era uno por sesión (el vocabulario de un test pasaba al siguiente); ahora uno por test. La caché de política de bloqueo de login y su respaldo en memoria se vacían en cada test (`tests/conftest.py`).
Tests: `tests/test_auditoria_2026_11_segunda_huecos.py` (también #26: auditoría de rotación de slug CAB, secreto OAuth y token de agente CMDB, ORG_SWITCH, evidencia de cumplimiento; espera de workflow y cola de automatizaciones en la empresa de cada fila).
- **Barrido final — errores al cliente:** `/clients|customers/{id}/health-composite` ya no devuelve `«Error interno: {e}»`; un `ErrorDeDominio`/`HTTPException` conserva su código (un 403 salía como 500); solo `ValueError` → 400. `POST /documents/{id}/ai-summary`: 503 «AI summary unavailable» sin el texto del proveedor (podía citar parte de la clave); `PresupuestoDeIAAgotado` sigue en 429. `POST /ai-modules/voice/transcribe` (500): sin el texto de la excepción.
- **Barrido final — fechas mal formadas:** `bookings/conflicts|gantt-leveling` (`start_date`, `end_date`), `capacity/board` (`week_from`, `week_to`) y `resource-forecast/weeks|users/{id}|availability` (`from_date`, `to_date`) se tipan `date`: 422 en vez de 500. `POST /capacity/plans` con `week_start`/`planned_hours` inválidos: 400.
- **Barrido final — índices:** migración `163_indices_de_claves_ajenas_calientes` (idempotente, `CONCURRENTLY` en PostgreSQL) + `index=True` en los modelos: `sd_tickets.requester_client_id|created_by_user_id|ci_id|problem_id`, `sd_agent_group_members.group_id`, `client_messages.parent_id`, `user_skills.skill_id`, `budgets.project_id`, `subcontractor_timelogs.project_id`, `tasks.parent_task_id`, `approval_steps.workflow_id`, `rate_entries.table_id` (las 12 claves ajenas sin índice más filtradas en `app/`; quedan ~370 sin índice propio, poco usadas).
- **Barrido final — nginx:** `location = /index.html` repite las cabeceras de seguridad del `server` (su `add_header` anulaba la herencia: la SPA salía sin CSP, X-Frame-Options ni nosniff); estáticos con `nosniff`. CSP alineada con la de `app/main.py`: fuentes de Google, `img-src blob:`, `media-src 'self' blob:`, `object-src 'none'`; `Permissions-Policy` `microphone=(self)` (comando de voz).
- **Barrido final — `.env.example`:** añade `INBOUND_EMAIL_SECRET`, `WEBAUTHN_RP_ID`, `WEBAUTHN_ORIGIN` (sin ellos producción no arrancaba); `AZURE_AD_*` → `AZURE_TENANT_ID|CLIENT_ID|CLIENT_SECRET` (los nombres que lee `Settings`).
- **Barrido final — métricas:** `METRICS_MULTIPROC_DIR` se lee de `PROMETHEUS_MULTIPROC_DIR` (la documentada; pydantic-settings v2 ignoraba `env=` y solo leía `METRICS_MULTIPROC_DIR`) o de `METRICS_MULTIPROC_DIR`.
- **Barrido final — dependencias:** `pypdf 6.21.4`, `pyasn1 0.6.5`, `certifi 2026.10.18`, `dnspython 2.9.2`, `urllib3 2.8.0`, `aiohttp 3.14.4`, `anyio 4.14.2`, `PyJWT 2.15.0`; ML: `transformers 5.10.4`, `sentence-transformers 5.6.0`, `fsspec 2026.6.0`; frontend `axios ^1.21.1` (arrastra `follow-redirects 1.16.3`). Pendientes por ser mayores o sin parche: `pillow 13`, `opentelemetry-* 1.45` (juego acoplado), `setuptools ≥83` (torch), `filelock 4`, `torch 2.13`, `zod 4`, `python-jose`/`ecdsa` (sin versión corregida).
Tests: `tests/test_barrido_final_2026_11.py`.
- **Errores de queries (frontend):** `QueryCache.onError` (main.tsx) publica en `lib/queryErrorBus.ts` y
  `ToastProvider` lo muestra como aviso de error (texto del `detail` o `toast.load_error`). Antes una
  query fallida dejaba `data` en `[]` y se veía como lista vacía. Sin aviso: `meta: { errorToast: false }`
  (la página ya pinta el error), 401 (refresco/sesión caducada), 429 (ya avisa AuthContext) y
  cancelaciones; el mismo texto en 3 s sale una vez. Las mutaciones no pasan por aquí (llevan su
  `onError`). `ResourceSchedulerPage` (previsión, proyectos, reservas) y la tabla de `CMDBPage` pintan
  el error en la página (`role="alert"`) en lugar del vacío.
- **Métricas multiproceso (docker-compose):** el servicio `api` define `PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus-multiproc`
  (merge del ancla `&app-env`, el resto del entorno no cambia) y su `command` pasa por `sh -c` para
  vaciar y crear el directorio antes de `exec uvicorn … --workers ${API_WORKERS:-4}`. Antes /metrics
  devolvía solo el registro del worker que atendía el scrape. `app/core/metrics.py` ya usaba
  `MultiProcessCollector` con la variable definida (sin cambios). `setup.sh` usa este compose; solo
  cambian una variable y el comando.
- **Vista previa de PDF:** `DocumentsPage` incrusta `download_url` en un `<iframe>`; con almacenamiento
  local es `/api/v1/documents/file/…`. La CSP de la API lleva `frame-ancestors 'self'` en esas rutas
  (antes `'none'`, que bloqueaba aunque `X-Frame-Options` ya fuera `SAMEORIGIN`) y nginx tiene
  `location ^~ /api/v1/documents/file/` con `add_header` propio para no heredar `X-Frame-Options: DENY`
  ni la CSP del servidor. El resto de la API sigue en `DENY`/`'none'`.
- **Dependencias:** `pillow 13.0.0` (12.3.0 tenía 42 avisos; PIL abre subidas en
  `documents_service` y `collaboration/_thumbnails`).
- **JWT solo con PyJWT:** python-jose (PYSEC-2026-4298) y ecdsa (PYSEC-2026-1325) no tenían versión
  corregida. Los 8 módulos de `app/` que usaban `jose` (security, tokens_y_cookies, client_portal
  endpoint y servicio, bi_embed_service, sla_service, approval_engine/por_correo, entrada_service) pasan
  a `import jwt` (PyJWT 2.15.0, ya en requirements). Mismos algoritmos, mismas cabeceras `kid` del
  llavero de `key_management`, mismas validaciones de `exp`/`aud`/`iss`/`sub`/`jti`; `JWTError` →
  `jwt.PyJWTError` y `jwt.ExpiredSignatureError` con las mismas respuestas HTTP (401/None). Única
  diferencia de PyJWT: un `iat` en el futuro (más allá del leeway, 0) se rechaza; python-jose solo
  comprobaba que fuera entero. Los tokens propios ponen `iat` = ahora o no lo llevan. Se quitan de
  requirements `python-jose`, `ecdsa`, `rsa` y `pyasn1` (`pip show`: sin otro dependiente).
- **OpenTelemetry 1.35 → 1.45.2** (CVE-2026-114603, CVE-2026-126360) como juego coherente:
  api/sdk/exporter-otlp 1.45.2 e instrumentaciones fastapi/sqlalchemy 0.66b2.
- **setuptools 81 → 84.2.1, torch 2.11 → 2.15.0, filelock 3.25.2 → 4.2.10:** torch ≥ 2.13 dejó de
  exigir `setuptools<82`, que era lo que bloqueaba PYSEC-2026-3447 y GHSA-xmj3-9gf7-h52w.
- **Prometheus multiproceso:** el supervisor de uvicorn no ofrece ganchos (desde la 0.30 reinicia el worker que muere, con otro PID, sin avisar), así
  que cada worker, al cerrar su `lifespan` (`_parar_servicios`), llama a
  `metrics.marcar_worker_terminado()` → `mark_process_dead(os.getpid())` y borra sus
  `gauge_live*_<pid>.db` (p. ej. peticiones en curso, `livesum`). Para los que mueren sin apagado
  (SIGKILL, OOM), cada scrape de /metrics marca muertos los PID de esos ficheros que ya no existen
  (solo POSIX: en Windows `os.kill(pid, 0)` mataría el proceso).
- **zod 3.25 → 4.6.7** (GHSA-mrhx-c7xc-m3w5, alta): `z.ZodIssueCode.custom` → `'custom'`;
  `invalid_type_error` → `error`; `.trim().email(msg)` → `.trim().pipe(z.email(msg))` (se recorta antes
  de validar, como antes); `ZodSchema`/`ZodIssue` (obsoletos) → `ZodType`/`core.$ZodIssue`.
  `ProjectsPage` reutiliza `getFirstIssueByField` en vez de su copia (con v4 `path` admite `symbol`).
  Los mensajes por defecto de zod cambian de texto; todos los esquemas usan mensajes propios.
- **numpy 1.26.4 → 2.5.4 (pin alineado con el entorno real):** el venv ya tenía 2.5.4 frente al pin
  1.26.4. 2.5.4 es la versión que elige el resolver de pip con `requirements.txt` + `requirements-ml.txt`
  sin fijar numpy. Ningún paquete fijado pone techo salvo statsmodels (`<3`), y las transitivas scipy
  (`>=2.0,<2.8`) y contourpy (`>=2.0`) ya no admiten 1.x. Se fija en los dos ficheros. Verificado con el
  resolver sobre los ficheros fijados, `pip check` y ajustes reales de prophet, statsmodels
  (Holt-Winters, ARIMA), scikit-learn, lightgbm y duckdb.
Tests: `tests/test_segunda_auditoria_2026_11_infra.py`, `frontend/src/__tests__/queryErrorBus.test.tsx`.
- **Paridad PostgreSQL columna a columna (#5):** `alembic upgrade head` sobre un PostgreSQL 16 vacío
  comparado con `Base.metadata` (`compare_metadata` con `compare_type` y `compare_server_default`)
  daba 152 diferencias: 3 reales, todas en `budgets` (la 144 añadió las columnas sin lo demás):
  faltaba la clave ajena `cliente_id → clients.id ON DELETE SET NULL` y los índices
  `ix_budgets_estado` e `ix_budgets_origen_id`. Las crea la revisión
  `164_paridad_postgres_e_indices_de_claves_ajenas`; antes pone a NULL los `cliente_id` huérfanos
  (lo mismo que haría la clave al borrar el cliente). El resto es ruido y se admite uno a uno:
  15 índices solo de PostgreSQL (10 trigramas de la 083, 4 únicos parciales `WHERE is_active`, el
  único de expresión `ux_audit_logs_cadena` de la 137), 80 `server_default` de relleno que la base
  tiene y el modelo no, todos con el mismo valor que su `default=` de Python (comprobado valor a
  valor; si difiere cuenta como real), y 54 índices de claves ajenas que la 073 creaba y el modelo
  no declaraba (resuelto con `index=True`, ver abajo). Tras la 164: 0 reales. La comprobación vive en
  `scripts/paridad_postgres.py` (`--url` sobre una base ya migrada, ~35-60 s; `--servidor … --migrar`
  crea una base y migra, ~2 min más) y la usa
  `tests/test_alembic_schema_parity.py::test_alembic_upgrade_head_sobre_postgres_coincide_con_los_modelos`
  (`slow`, se salta sin PostgreSQL). Antes ese test admitía cualquier `remove_index` y no comparaba
  defaults.
- **Índices en todas las claves ajenas (#12):** medido con un barrido de `Base.metadata` y del
  inspector de PostgreSQL (FK sin índice, único o PK cuya primera columna sea la FK): modelos 371 de
  1215 → 0; base migrada 316 de 1214 → 0 (1215 con la nueva FK de `budgets`). Los modelos llevan
  `index=True` en las 371 columnas (62 ficheros de `app/models`, más `client_user_projects.project_id`,
  segunda columna de su PK); la 164 crea los 317 índices que faltaban en la base (idempotente,
  `CONCURRENTLY` en PostgreSQL, nombres `ix_<tabla>_<columna>`) y su downgrade solo quita los suyos.
  No se excluyó ninguna por tabla pequeña: sin datos de producción no hay con qué justificarlo.
- **Las 3 rutas sin explicar de `RUTAS_ESPERADAS` (#10):** con `git archive` de cd383a6c (1044 pares
  con guarda), e7cbeecf (1044) y 4aad8fde (1047) y el diff de `RUTAS`, las tres son
  `PUT` y `DELETE /api/v1/integrations-hub/jira/config` y `POST /api/v1/integrations-hub/jira/sync`,
  todas `require_admin`, que entraron con la 161 (hub de Jira a `jira_config`) sin subir el número.
  Guarda de rol y ABAC (prefijo `/api/v1/integrations-hub`) correctos; las tres resuelven la conexión
  por `current_user.organization_id`. Pero el sync recorría `Task` con `jira_issue_key` sin filtrar por
  organización y dependía del filtro automático de tenant, que no corre para superadmin: con el Jira de
  una organización se reescribía el estado de tareas de otras. `sincronizar_tareas_con_jira` recibe
  ahora `org_id` y filtra `Task.organization_id` (sin organización, no toca nada).
- **Voz de Twilio con varias organizaciones (#19):** la organización sale del número llamado (`To`).
  Cada organización declara sus números en el ajuste en vivo nuevo `TWILIO_PHONE_NUMBERS`, del grupo
  `service_desk` (E.164 separados por comas; también está en `ServiceDeskSettingsMixin`). La credencial
  `twilio.from_number` también cuenta. La firma se comprueba con el token de esa organización
  (credencial `twilio.auth_token` o ajuste `TWILIO_AUTH_TOKEN`) y, si no tiene, con el global, igual
  que ya hacía el SMS. La llamada y la opción DTMF se atienden con `como_organizacion`, y la sesión se
  guarda en la organización y no sin ella. **Antes se atendía cualquier número sin organización; ahora
  se rechaza** con `<Reject/>` todo número que no declara nadie, que declaran dos organizaciones o que
  es de una organización desactivada: 200 si la firma global es válida, 403 si no. Firma inválida →
  403. El token de una organización no vale para el número de otra. El callback `/gather` solo anota
  en sesiones de la organización del número. El webhook de voz respondía **500 a toda llamada**
  (`create_session` devuelve `{session, greeting}` y se leía `session["id"]`). El texto de la
  configuración del IVR se escapa antes de meterlo en el TwiML. SMS: usa el mismo resolutor
  (`sms_service.organizacion_del_numero_de_twilio`), así que un número en `TWILIO_PHONE_NUMBERS` también
  enruta SMS. Un `from_number` repetido en dos organizaciones ya no se asigna a la primera que
  devuelve la consulta. Tests: `tests/test_twilio_voz_multiorganizacion.py`.
- **Enlaces de la documentación (#16):** se comprobaron con un script todos los enlaces relativos y anclas
  de `docs/**/*.md`, `README.md` y `DOCS.md`: 1 roto antes y 0 después.
  `docs/AI_ML_ARCH_DECISIONS.md` enlazaba `app/services/stt/` relativo a `docs/`; ahora enlaza
  `../app/services/stt/`.
- **Guía de despliegue (#21):** `docs/DESPLIEGUE.md` es la lista ordenada para el operador: copia de
  seguridad, variables nuevas y de dónde sale cada valor, migraciones 158–164 (qué hace cada una, cuáles
  bloquean y cuáles usan `CONCURRENTLY`, y cómo detectar índices INVALID) y pruebas de humo. Está
  enlazada desde el README.
- **Listados paginados (#7):** un barrido AST de `app/services` contó 163 funciones `list_*` que hacían
  `.all()` sin tope. Mecanismo único en `app/core/paginacion.py` (`Paginacion`, `paginacion`, `paginar`,
  `paginar_lista`, `exponer`, `lista_paginada`), con la convención que ya usaba la API y que recorre
  `todasLasPaginas` en el frontend: `page`/`page_size` (máximo `MAX_TAMANO_DE_PAGINA`), total en
  `X-Total-Count` (+ `X-Page`/`X-Page-Size`) y en `meta.total`/`meta.has_more`. Sin `page_size` la
  respuesta es la de antes, hasta el nuevo ajuste `LIST_MAX_ROWS` (5000): si se llega a él, `X-Truncated:
  true`, `meta.has_more=true` y un aviso en el log; nunca se corta en silencio. Aplicado a: `/alm/vendors`,
  `/alm/contracts`, `/alm/licenses`, `/alm/assets`, `/expenses/my`, `/expenses/pending`, `/expenses/team`
  (los totales salen ahora de un agregado SQL sobre todos los filtrados, no de la página),
  `/timesheets/pending`, `/timesheets/team`, `/gdpr/requests` (estos tres aceptaban `page`/`page_size` y
  los ignoraban), `/clients` (ídem; `limit` sigue siendo «las primeras N»), `/clients/{cid}/invoices`,
  `/imputations/alerts`, `/revenue/entries`, `/governance/compliance/evidence`, `/forms/{id}/submissions`.
  `contract_service.list_contracts` y `expense_service.list_team_expenses` se borraron (sin llamadas; el
  endpoint usa `query_contracts` / `team_expenses_page`). `ResponseMeta` ya tenía `has_more`;
  `APIListResponse.ok` acepta ahora `has_more`.
- **`/clients/{cid}/invoices` daba 500:** leía `Invoice.total_amount`, que no existe; el importe es
  `Invoice.total` (la clave de la respuesta sigue siendo `total_amount`). Además ahora es una consulta (antes
  tres más la unión en Python) y carga el proyecto de una vez.
- **N+1 (#8):** medido con un contador `before_cursor_execute` (consultas por petición con 2 → 8 filas):
  `/sd/tickets` 18→30 a 15→15 (`get_tickets_dynamic_fields`, en lote: antes 2 consultas por ticket);
  `/alm/vendors` 12→18 a 12→12; `/alm/contracts` 18→42 a 13→13; `/alm/licenses` 18→42 a 13→13
  (clientes enlazados en una consulta, `_clientes_vinculados`, y `selectinload`/`joinedload` de lo que leen
  los serializadores); `/alm/assets` 15→27 a 12→12; `/invoices` y `/billing-reports/invoices` 17→35 a
  13→13 (`query_invoices` carga proyecto y líneas); `/clients` 4 `count` + gestor por cliente a 15→15
  (`recuentos_de_clientes`, cuatro `GROUP BY` por página); `/imputations` 20→26 a constante (la tarea de
  cada imputación con sus comentarios y sus imputaciones para `real_hours`: el `lazy="selectin"` de
  `Task.imputations` no se aplica al llegar desde una imputación). Sin crecimiento ya, medidos y sin tocar:
  `/projects` 16, `/tasks` 18, `/contracts` 12, `/documents` 15, `/users` 22, `/enterprise/audit-log` 11,
  `/projects/{id}` 14, `/projects/{id}/members` 10, `/tasks/{id}` 17, `/sd/tickets/{id}` 19,
  `/epics?project_id=` 10. Los helpers por fila (`get_linked_clients_for_*`) ya no tragan excepciones: un
  fallo de la consulta sale como error en vez de una lista vacía. Tests:
  `tests/test_listados_paginados_y_sin_n_mas_1_2026_11.py`.
- **Detrás de nginx: esquema, IP del cliente y firma de Twilio (#23).** nginx no termina TLS y mandaba
  `X-Forwarded-Proto $scheme` (siempre `http`), uvicorn solo cree cabeceras de 127.0.0.1 y la IP de nginx en
  la red de compose cambia en cada arranque: la API veía `http://…`, la firma de Twilio (sobre la URL https)
  no cuadraba y todo SMS/llamada daba 403; el `Location` de tus salía en http. Ahora:
  · nginx respeta el `X-Forwarded-Proto`/`-Host` del proxy de delante (o pone el suyo) y manda
  `X-Forwarded-Host` en todos los `proxy_pass`.
  · `EsquemaDelProxyMiddleware` (`app/core/network.py`, el más externo) aplica `X-Forwarded-Proto` al esquema
  si la IP que conecta está en `TRUSTED_PROXY_CIDRS` con `TRUST_PROXY_HEADERS` activo: la misma política, con
  redes, que ya decidía `X-Forwarded-For`/`-Host`. No se usa `--forwarded-allow-ips` de uvicorn (con la 0.54
  admite redes, ver #30): sustituiría el cliente por la IP reenviada antes de que la app lo vea, y entonces
  `extract_host` no reconocería a nginx y no aplicaría `X-Forwarded-Host`; serían dos políticas. compose arranca uvicorn con `--no-proxy-headers` y fuerza
  en `api` `TRUST_PROXY_HEADERS=1` y `TRUSTED_PROXY_CIDRS=${CONTECFLOW_PROXY_CIDRS:-10.0.0.0/8,172.16.0.0/12,192.168.0.0/16}`
  (la API no publica puerto: solo la alcanza la red de compose).
  · `extract_client_ip` recorre `X-Forwarded-For` de derecha a izquierda y devuelve el primer salto que no es
  proxy de confianza. **Cambio de comportamiento:** antes tomaba el primero, que lo pone el cliente, así que
  con la confianza activa cualquiera elegía su IP ante el rate limiting.
  · Twilio (SMS y voz) comprueba la firma contra `BACKEND_URL` + ruta y consulta (lo que recomienda Twilio
  detrás de proxies) y, si no, contra `request.url`. Las dos son la misma ruta: una firma no vale en otro
  endpoint. **`BACKEND_URL` tiene que ser la URL pública** (con compose, la del dominio).
  · Auditadas el resto de firmas: Stripe (`t.cuerpo`), Slack (`v0:ts:cuerpo`), DocuSign, Jira, GitHub, CAB
  (HMAC del cuerpo), GitLab y Adobe Sign (secreto/ClientId en cabecera) y Teams (JWT de Bot Framework, sin
  URL) no dependen de la URL: no les afecta. Tests: `tests/test_twilio_detras_de_proxy.py`.
- **`.env.example` (#23):** añadidas las variables que un operador necesita y faltaban (proxy, KMS, rate
  limit, ClamAV, SCIM, GeoIP, métricas, Sentry/OTel, Slack/GitHub/GitLab, DocuSign/Adobe Sign, Stripe, Teams,
  OAuth del chat, LiveKit, VAPID, STT, OpenSearch/NATS, tipos de cambio, `APP_PUBLIC_URL`,
  `CONTECFLOW_PROXY_CIDRS`). Las opcionales sin valor por defecto, comentadas; `PROMETHEUS_MULTIPROC_DIR` y
  `OTEL_*` comentadas a propósito (sus SDK actúan con que la variable exista, aunque esté vacía, y compose
  pasa el `.env` a worker y beat). Los ajustes finos se quedan fuera y el pie del fichero dice cuáles.
  `tests/test_env_example_sincronizado.py` falla si aparece un campo de Settings sin decidir, un secreto sin
  declarar o una variable activa que no lee nadie.
- **uvicorn 0.29.0 → 0.54.0 y httptools 0.7.1 → 0.9.0 (#30).** La 0.54 (25-09-2026) es la estable actual
  y exige `httptools>=0.8.0`; fastapi 0.135.3 y starlette 1.3.1 no la acotan, así que no cambian.
  `pip check` limpio. Lo que cambia en marcha, según las notas de versión:
  · `--workers`: supervisor nuevo (0.30) que **reinicia** el worker que muere y comprueba su salud
  (`--timeout-worker-healthcheck`, 0.37); si un worker falla al arrancar sale con código 3 y el supervisor se
  para en vez de reintentar sin fin (0.50); `SIGHUP` reinicia los workers de uno en uno (0.51). El gancho de
  Prometheus no cambia: cada worker se da de baja al cerrar su `lifespan` y los que mueren sin cerrarlo se
  limpian en el siguiente scrape (POSIX); el que lo sustituye llega con otro PID.
  · WebSocket: `--ws auto` usa ahora la implementación `websockets-sansio` (0.50; la heredada queda
  obsoleta), con cierre completo del handshake y ping de keepalive. `websockets==16.0` ya cumple su mínimo (13).
  · Lifespan: el apagado se ejecuta también si la salida llega durante el arranque (0.41).
  · Proxy: `FORWARDED_ALLOW_IPS` admite redes (0.31) y por defecto confía también en `::1` (0.53). El
  diseño de #23 se mantiene (una sola política en la app; compose con `--no-proxy-headers`): ver arriba por qué
  delegarlo en uvicorn rompería `X-Forwarded-Host`.
  Ningún código usa APIs retiradas (`uvicorn.workers`, `LifespanOn.error_occured`).

- **Tipado de las respuestas del cliente (tarea #13):** las 969 llamadas de `services/api/_core.ts` declaran su respuesta (640 sin tipo antes), comprobada contra el backend; `as unknown as` en `src` de 62 a 20 (los que quedan no leen respuestas: `import.meta`, `Intl`, prototipos, estilos, formularios). Correcciones de contrato que cambian lo que se ve o se manda:
  - Facturas: `InvoiceOut` incluye `client_address` y cada línea `source_ids` (guardar un borrador desde la ficha borraba la dirección y soltaba las horas facturadas); la última sincronización contable se lee por integración y los pendientes de `invoices.pending_sync` (salía siempre «Sin sincronizar»).
  - Costes de personal: borrar un override de país funciona (`confirmar()`; `openConfirmGlobal` devolvía `void`). Hitos: el modal de rechazo muestra `name` y `billing_amount`.
  - BI v2: la lista de presets se lee como lista (salía vacía). RGPD BI: el interruptor cambia el consentimiento de la finalidad de la fila (antes siempre `analytics`); el informe de `erasure-execute` se ve tras borrar; sin plazo de 30 días en duro. Query Builder y Previsión BI: operadores, agregaciones y métodos salen del servidor. Alertas BI (panel compacto): sin condiciones de umbral, que exigen `threshold`.
  - Voz: `process_voice_core` devuelve `pending_action`, `confirmed` y `execution_id` (vuelve «Confirmar»). Reuniones IA: el alta manda `participants` como lista y `duration_min` (antes 422 siempre). NexusAgent: el historial abre la ejecución completa y cuenta `steps_count`. BI: la tabla de salud usa `project_id/name/code`; el cuadro de proyectos no manda fechas a `projects-health` ni `kpis`.
  - Service desk: el asistente RCA guarda la última respuesta antes de cerrar (daba 400 siempre) y lee `completed`; la cola lee `assigned_to_name` (salía «Sin asignar»); el historial de formularios dinámicos se lee como lista; la asignación ML muestra `components` y la carga de `agent_loads`.
  - Proyectos: el Gantt del proyecto lee `/tasks/dependencies` (nunca mostraba dependencias); las fases de una plantilla nueva mandan `estimated_weeks`. Sprints: la retrospectiva carga las notas con `useEffect`. Panel de equipo: OKR por `progress` y `active`. Épicas: avance de `/epics/roadmap`. Búsqueda NQL: manda `entity_type` (antes 422). Dependencias: sin columna «Nota». La ficha del proyecto muestra el asignado de `assignee.full_name` (`assignee_name` no existe).
  - Rollout de cambios: `simulatePlan` sin cuerpo (simulaba una carga vacía) y la lista de planes ya no sale vacía. Timesheets: las líneas traen `is_approved` y la etiqueta facturable lee `billable`. Menciones: se lee `context`. Cronómetro: el historial pide solo las imputaciones del usuario.
  - Documentos: el listado pide `page_size` (con `limit` llegaban 50); la reserva propia se reconoce en el listado. Wiki: la visibilidad del editor se guarda por `PATCH …/visibility`; editar una subpágina conserva padre, orden y publicación; el portal lista subpáginas; recuento por etiqueta con `page_count`. Formularios públicos de tareas: piden proyecto destino (antes 400). Alertas: resolver o leer refresca `alerts-count`.
  - Jira: importar exige proyecto (`/jira/sync` sin `project_id` → 500); la tabla de issues lee `{total, issues}`; la pista del token es `jira_api_token_hint`. Gobierno IA: el registro muestra `action_type`. Portal de desarrolladores: el alcance `expenses` se puede elegir.
  - Recursos: el selector de orden ya no rompe la página (pasaba un objeto como clave a `useSort`).
  - Selectores de personas de Tareas, Proyectos (equipo y PM de plantilla), RACI, Formación y `UserSelect`: `/users/directory` (el subcontratado recibía 403 de `/users`).

- **Fallos de backend hallados al tipar el frontend** (tests en `tests/test_auditoria_tipado_backend_2026_11.py`):
  - Seguridad. `GET /ai/agent/{id}`: solo el dueño de la ejecución (como el historial y el sondeo); antes cualquiera con el id. `/sd/alert-clusters*`: un `organization_id` explícito solo vale si es el propio o si llama un superadmin (404 si no); antes un tenant leía o escaneaba los clusters de otro. CMDB 3D: filtra por organización y, sin CIs, devuelve un grafo vacío (la pantalla lo dice) en vez de 8 CIs de demostración inventados. Voz: el resumen de proyecto (y la búsqueda de proyecto de imputar y crear tarea) pasa por `scope_projects_query`.
  - Fallos 500/422. Export UAT con tarea enlazada (`c.task_title` no existía). `POST /jira/sync` sin `project_id`: actualiza las tareas enlazadas y omite las incidencias nuevas (`skipped_without_project`); con un proyecto inexistente o no visible, 404. E-firma: ids de sobre, documento, firmante y usuario como UUID (`str`); antes no se podía crear un sobre. Git: `PROut`/`DeployOut`, los filtros y las rutas `/pull-requests/{pr_id}` y `/tasks/{task_id}/*` usan ids `str` (UUID), igual que `git_service`; listar un PR real daba 500.
  - RGPD: `erasure-execute` borra y resuelve en un paso (`resolve_dsr(..., execute_erasure_pipeline=True)`); antes, tras borrar, volvía a escribir el id del interesado en consentimientos e historial y la solicitud quedaba con el id en claro. Previsión BI por lotes: una métrica inválida va a `errors` y no tira el lote, y el lote ya no gasta el límite del endpoint individual. O365: la adopción tiene la misma forma con y sin datos (`by_product`; `products` desaparece).
  - Auto-resolución: la config se lee y escribe por organización (antes la global, que heredan todas) y las estadísticas leen el feedback de la organización. Incidentes mayores: fechas ISO 8601. Reglas de encaminamiento: `conditions`/`actions` como objetos (el frontend ya no hace `JSON.parse`). Timesheet: sin imputaciones borradas.
  - Skills: cualquier usuario interno quita sus propias skills (antes solo admin/RR. HH., aunque podía añadirlas); la skill ha de ser del usuario de la ruta. Certificaciones: editar y borrar responden con `APIResponse`; al editar, solo admin/RR. HH. cambian el titular. Inscripciones: `status` se valida contra `CourseStatus` (`cancelled`; `dropped` no existe → 422).
  - Menciones (`GET /activity/mentions/my`): paginación común (`page`/`page_size`, total en `meta`/`X-Total-Count`) en vez de `limit` ≤ 100; el texto es `context_text`, como en `/epics/mentions`, y `context` queda como alias obsoleto para clientes externos. UAT: un caso borrado no se edita ni se vuelve a borrar. `POST /organizations/{id}/impersonate`: sobre `APIResponse` (`data` + `meta`). `GET /portfolios`: la página se aplica de verdad (antes devolvía todas y solo copiaba `page` al `meta`).
  - BPMN: la clave de un proceso propio no puede repetir la de un proceso global del catálogo que la organización ve (`clave_unica` → sufijo); en el listado, la copia propia de una clave global (la de `seed_catalogue`) sustituye a la global. El índice único en BD que cierra la carrera llegó en la migración `168_indice_unico_procesos_bpmn` (#33).

## 3. Estructura del repositorio
- `app/`: backend
- `alembic/`: migraciones de base de datos
- `frontend/`: SPA web
- `tests/`: suite de tests backend
- `tests_e2e/`: pruebas end-to-end
- `scripts/`: utilidades operativas (`ci_local.sh`, copias, despliegue, rotación de claves, semillas)
- `docs/`: documentación por tema (diseño, Service Desk, observabilidad, despliegue en `docs/DESPLIEGUE.md`)
- `deploy/`: Dockerfile del backend y del frontend; `docker-compose.yml` en la raíz
- `uploads/`: almacenamiento local de ficheros cuando no hay S3

Detalle medido (número de ficheros, módulos y modelos): README, «Technical guide → 2. Repository layout».

## 4. Requisitos
- Python 3.12
- Node.js 20 (`setup.sh` solo avisa por debajo de 18; la imagen del frontend usa `node:20-alpine`; Vite 7 pide Node ≥ 20.19 según su documentación, no comprobado aquí)
- npm
- Redis (broker de Celery, rate limiting, tickets de WebSocket); `setup.sh` lo levanta con Docker
- Docker con Compose v2 (opcional en desarrollo; sin él `setup.sh` cae a SQLite)

Opcional:
- PostgreSQL para entorno similar a producción

## 5. Instalación
### Backend
1. Crear entorno virtual: `python -m venv venv`
2. Activar entorno:
   - macOS/Linux: `source venv/bin/activate`
   - Windows: `venv\Scripts\activate`
3. Instalar dependencias: `pip install -r requirements.txt`

### Frontend
1. `cd frontend`
2. `npm install`

## 6. Configuración
### Backend
Crear `.env` desde `.env.example`.
Variables críticas:
- `DATABASE_URL`
- `SECRET_KEY`
- `REDIS_URL`
- `ALLOWED_ORIGINS`
- claves de proveedores IA si aplica

`ENVIRONMENT` vale `production` si no se define (`setup.sh` escribe `development` en `.env` cuando falta). Lista completa de variables de `Settings` (475, con sus valores por defecto) y de los ajustes editables en caliente (256 claves en 24 grupos): README, «Technical guide → 4. Configuration».

### Frontend
No hace falta `frontend/.env`: sin `VITE_API_URL` el cliente usa `/api/v1` y el proxy de Vite reenvía `/api` a `http://localhost:8000`. Si se define `VITE_API_URL` (API en otro origen), tiene que terminar en `/api/v1`: axios usa ese valor como base y sin el sufijo las llamadas irían a `/auth/login` y fallarían. `frontend/.env.example` lo explica y deja todo comentado.

## 7. Arranque local
### Modos de `setup.sh` / `setup.bat`
- `./setup.sh demo` — carga seed y arranca.
- `./setup.sh clean` — limpia datos y deja solo admin, luego arranca. El reset crea automáticamente una organización base y asigna el usuario admin a esa organización para cumplir la restricción multi-tenant actual.
- `./setup.sh start` — arranca y preserva la base de datos existente; antes aplica las migraciones pendientes (`alembic upgrade head`) y se detiene si fallan.
- `demo`, `clean` y `start` arrancan la API (8000, `ENABLE_APSCHEDULER=0 ENABLE_CELERY_BEAT=1`), un worker y un beat de Celery (registros en `/tmp/contecflow-worker.log` y `/tmp/contecflow-beat.log`) y Vite (3000). Puertos cambiables con `BACKEND_PORT`/`FRONTEND_PORT`.
- `./setup.sh stop`, `update`, `docker-stop`, `docker-clean` — parar, actualizar y parar o borrar la infraestructura Docker.
- `clean`, `demo` y `docker-clean` se niegan (salida 2) si `ENVIRONMENT` no es de desarrollo o pruebas.
- `setup.bat` tiene los mismos modos que `setup.sh` (`demo`, `clean`, `start`, `stop`, `update`, `docker-stop`, `docker-clean`) más `install` (instala y pregunta el modo), `start demo|clean` y la variable `SETUP_INIT_MODE=demo|clean`. Sin argumentos muestra la lista de opciones. `setup.bat start` sin modo conserva la base de datos.

### Opción manual
1. API backend: `ENABLE_APSCHEDULER=0 ENABLE_CELERY_BEAT=1 uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` (con beat en marcha; si APScheduler y beat están activos a la vez la API no arranca. Sin beat, `ENABLE_APSCHEDULER=1`, el defecto, replica en el proceso todo el `beat_schedule`)
2. Worker Celery: `celery -A app.worker.celery_app worker --loglevel=info`
3. Beat Celery: `celery -A app.worker.celery_app beat --loglevel=info`
4. Frontend (en `frontend/`): `npm run dev`
5. Documentación OpenAPI: `http://localhost:8000/api/v1/docs` (desactivada con `ENVIRONMENT=production` salvo `EXPOSE_API_DOCS=1`)

### Paridad de autenticación y despliegue
- El login ahora soporta MFA por TOTP y passkeys, con un flujo de UI coherente con el patrón de Contecmind.
- El flujo incluye carga de proveedores SSO, redirección al proveedor y manejo del challenge MFA antes de completar la sesión.
- El stack de Docker está en `docker-compose.yml`, en la raíz (PostgreSQL, Redis, S3, migrate, api, worker, beat y web); `deploy/` guarda los Dockerfile. Copias: `scripts/backup.sh` y `scripts/restore.sh`; despliegue: `scripts/deploy.sh`.

## 8. Base de datos

### Migraciones: Alembic es la ÚNICA fuente de verdad

```bash
alembic upgrade head          # aplica lo pendiente (idempotente)
alembic revision -m "…"       # nueva revisión
alembic heads                 # debe devolver UNA sola cabeza
```

Auditoría 2026-08 (hallazgo 11). Antes había **dos** caminos para construir el
esquema y sólo uno estaba completo:

| Caso | Camino anterior | Problema |
|---|---|---|
| BD nueva | `Base.metadata.create_all()` + `alembic stamp head` | `stamp` marca las revisiones aplicadas **sin ejecutarlas** |
| BD existente | `alembic upgrade head` | Es el único que ejercitaba la cadena |

Consecuencia: la cadena de revisiones **no se ejecutó nunca de principio a fin**.
Al probarla sobre una base vacía producía 374 tablas frente a las 392 de los
modelos — faltaban 19, entre ellas `expenses`, `email_templates`,
`automation_rules`, `revenue_recognition_entries`, `gdpr_requests` y
`webhook_triggers`. Un despliegue que hubiera pasado por Alembic se quedaba sin
esas funcionalidades. Se cerró con la revisión `089_schema_gap_missing_tables`.

Auditoría 2026-11: la cadena volvía a romperse sobre una base vacía (089 exigía dos modelos de ingresos ya retirados por la 156; 093 y 146 leían `organization_id` antes de que existiera; 138 hacía `ADD COLUMN` con clave ajena, que SQLite solo admite en modo batch; 137 importaba un módulo movido a `app/db/`). Corregidas sin cambiar lo que hacen sobre una base existente: `alembic upgrade head` llegaba entonces a la 158 desde cero, y lo vigila `tests/test_alembic_schema_parity.py`. A 16-11-2026 hay 123 ficheros de revisión en una cadena lineal con cabeza `169_bpmn_decisiones_y_codigos_de_error` (contados leyendo `revision`/`down_revision`; no se ha vuelto a ejecutar la cadena desde cero para esta revisión). `setup.bat` mantiene su atajo para bases nuevas (`create_all` + `stamp head`); `setup.sh` no se ha tocado.

Reglas que se derivan de eso:

- **Nunca** `create_all` en el arranque ni en el despliegue. Cada modelo nuevo
  necesita su revisión. `app/db/migrate.py` se borró (auditoría 2026-11): no lo usaba ningún flujo.
- `tests/test_alembic_schema_parity.py` levanta una base vacía, corre
  `upgrade head` de verdad y compara con los modelos. Es el test que faltaba.
- Una sola cabeza de migración. Dos significan ramas divergentes sin fusionar y
  `upgrade head` fallaría.

### Seed
- `python -m app.db.seed` (lo que usa `setup.sh demo`). `python scripts/seed_full_data.py` es otro generador, más pesado.
- Los usuarios salen de `seed_users_data.json`; `app/db/seed_parts/core.py::default_seed_users()` sólo se usa si falta ese fichero
  (ver `tests/test_seed_fixture_parity.py`).

Notas:
- SQLite local genera `.db-wal` y `.db-shm` durante ejecución.
- No versionar artefactos de BD local.

## 8bis. Stack Docker

Un único `docker-compose.yml` en la raíz, con la misma estrategia que contecmind
y contecweb. Los dos escenarios se distinguen con perfiles, no con ficheros
duplicados:

```bash
./setup.sh update                       # crea .env, volúmenes y levanta la infra
                                        # (sin argumento solo muestra el uso)
docker compose up -d                    # DESARROLLO: postgres + redis.
                                        # La app corre en local (uvicorn) y
                                        # guarda los ficheros en uploads/.
docker compose --profile s3 up -d       # + el almacén S3 (versitygw), para
                                        # probar el camino de S3 en local
docker compose --profile app up -d      # PRODUCCIÓN: + s3, migrate, api,
                                        # worker, beat y web (nginx)
docker compose --profile observability up -d   # + prometheus y exporters
docker compose down                     # apaga, conserva los datos
docker compose down -v                  # borra SÓLO los volúmenes regenerables
```

### Decisiones de diseño, y por qué

**Puertos siempre en `127.0.0.1`.** Con `"5434:5432"` Docker publica en 0.0.0.0.
Este fichero se copia para demos y preproducciones, y ahí eso significa un
Postgres, un Redis sin contraseña y un almacén S3 accesibles desde toda la red con
credenciales de desarrollo.

**Variables críticas con `${VAR:?}`.** Un valor por defecto silencioso en una
credencial es levantar el stack con credenciales conocidas sin enterarse. Con
`:?` el `up` aborta con un mensaje claro. `setup.sh` las rellena y genera los
secretos una vez, así que en desarrollo no hay fricción.

**Volúmenes de datos `external: true`.** Un `docker compose down -v` no puede
borrarlos. Es la lección de un incidente en contecmind, donde un `down -v`
recreó los volúmenes y se perdieron los metadatos y el índice de golpe. El coste
es que compose ya no los crea, así que `setup.sh::ensure_persistent_volumes` los
crea de forma idempotente.

**Imágenes con versión fija, algunas por digest.** Con un tag móvil dos
despliegues del mismo commit pueden levantar imágenes distintas y un fallo deja
de ser reproducible.

**`beat` es un servicio aparte.** Antes iba como `worker --beat` en el mismo
contenedor: con más de una réplica del worker, varios planificadores disparaban
la misma tarea periódica — informes y correos duplicados. Beat debe ser
singleton.

**Las migraciones son un servicio del que depende la API**
(`service_completed_successfully`), así que la aplicación no arranca con un
esquema a medias.

**La API no publica puerto al host.** Quien entra es nginx; publicarla saltaría
las cabeceras de seguridad y el tope de tamaño de cuerpo.

**Un almacén S3 en el stack.** `S3Service` no tenía `endpoint_url` configurable,
así que el backend de objetos nunca se ejercitaba fuera de AWS y los documentos
caían siempre al sistema de ficheros local. Con `AWS_S3_ENDPOINT_URL` el mismo
código sirve contra el almacén local y contra AWS (o cualquier S3 compatible) en
producción.

**El almacén es versitygw, no MinIO, y va bajo perfil (27-09-2026).** MinIO
cerró su distribución pública en dos pasos: Docker Hub el 17-09 y quay.io el
27-09, que contesta «Requires authentication» hasta para `:latest`. Con MinIO en
el `up` por defecto, eso tumbaba el arranque entero, y `setup.sh`, al ver fallar
el `up`, caía a SQLite sin decir por qué. Dos cambios:

- **El servidor es versitygw** (Versity S3 Gateway, Apache-2.0, de `ghcr.io`), el
  mismo que usan contecmind y contecweb. Con su backend `posix` cada objeto es un
  fichero normal del volumen y cada bucket una carpeta: el bucket se crea con un
  `mkdir` al arrancar y el servicio `minio-init` ya no existe.
- **Va bajo los perfiles `s3` y `app`.** En desarrollo la app no lo usa, así que
  no puede tumbar lo que sí se usa. Con `--profile app` arranca solo, porque ahí
  la API y el worker guardan los documentos en él.

Las variables siguen llamándose `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`,
`MINIO_BUCKET` y `MINIO_PORT`, para no romper ningún `.env` existente. El puerto
por defecto pasa de `127.0.0.1:9000` a **`127.0.0.1:9003`**: en esta máquina
conviven los productos de la casa y contecweb publica el 9000 (contecmind, el
9002). La consola web de MinIO (9001) desaparece: versitygw no tiene.

**Pasar datos de un MinIO antiguo.** El volumen nuevo es `contecflow_s3_data`, y
no se reutiliza `contecflow_minio_data`, porque MinIO guarda los objetos en su
formato (`xl.meta` y partes), no como ficheros. versitygw montado encima no
fallaría: serviría eso como si fueran objetos. Si un despliegue tiene documentos
en MinIO, se copian de servidor a servidor mientras el antiguo sigue levantado
(la imagen en caché de esa máquina aún arranca):

```bash
docker compose --profile s3 up -d s3
aws() { docker run --rm --network host -v "$PWD/copia-s3:/copia" \
  -e AWS_ACCESS_KEY_ID="$1" -e AWS_SECRET_ACCESS_KEY="$2" \
  public.ecr.aws/aws-cli/aws-cli "${@:3}"; }
# 1) del MinIO antiguo (9000) a un directorio del host
aws <usuario-minio> <secreto-minio> s3 sync s3://contecflow-documents /copia \
  --endpoint-url http://127.0.0.1:9000
# 2) del directorio al almacén nuevo (9003)
aws "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" s3 sync /copia s3://contecflow-documents \
  --endpoint-url http://127.0.0.1:9003
```

La copia va por la API de S3, no por el volumen: es lo único que lee bien los
dos formatos.

**Tres fallos de cliente que MinIO tapaba.** MinIO era permisivo; versitygw, como
AWS, no lo es. Al probar el camino completo (subir, firmar la URL y descargarla)
salieron tres, arreglados y con prueba en `tests/test_s3_clientes_firman_en_v4.py`:

1. **`S3Service` presignaba con la firma v2** (`AWSAccessKeyId=…&Signature=…`).
   boto3 solo usa la v4 en las URLs firmadas si se le pide; como las peticiones
   normales sí iban en v4, subir funcionaba y descargar daba un 400 («Please use
   AWS4-HMAC-SHA256»). AWS también rechaza la v2 en regiones y buckets nuevos.
2. **El almacén de colaboración** (`COLLAB_S3_*`), lo mismo, y además sin
   direccionamiento por ruta, que es lo único que entiende un servidor de un solo
   host.
3. **eSign leía el documento con un `boto3.client("s3")` sin configurar**: sin
   endpoint ni credenciales, preguntaba a AWS, fallaba y caía al disco, donde el
   documento no estaba. Firmar un documento guardado en S3 fallaba siempre fuera
   de AWS. Ahora usa el cliente de `S3Service`.

Y una de servidor: **versitygw comprueba la región de la firma** («the region
"eu-west-1" is wrong; expecting "us-east-1"»), como AWS. El compose le da la
misma variable que usa la app, `AWS_REGION` (defecto `eu-west-1`), para que no
puedan divergir.

**Sin métricas del almacén en Prometheus.** El job `minio` rascaba
`/minio/v2/metrics/cluster`. versitygw no expone métricas en ese formato, y un
objetivo que no contesta nunca es una alarma que se aprende a ignorar, así que se
quitó. La salud del almacén la vigila el healthcheck del compose (`/health`).

### nginx

`frontend/nginx.frontend.conf` sirve el frontend **y** hace de proxy inverso a
la API. Antes servía sólo estáticos, sin ninguna directiva `proxy_pass`: el
navegador cargaba la aplicación y ninguna llamada llegaba a destino — el
despliegue no podía funcionar.

Que la API salga por el mismo origen elimina CORS, permite cookies httpOnly sin
`SameSite=None`, y encaja con la comprobación de Origin del middleware CSRF.
Incluye negociación de WebSocket (sin ella el chat queda en reconexión perpetua),
`client_max_body_size`, y propagación de `X-Forwarded-For` — sin la cual el rate
limiting por IP contaría todas las peticiones como procedentes de nginx. La API
solo cree esas cabeceras (`X-Forwarded-For`, `-Host`, `-Proto`, `X-Real-IP`) si
`TRUST_PROXY_HEADERS` está activo **y** la IP que conecta está en
`TRUSTED_PROXY_CIDRS` (`app/core/network.py`); el compose lo fija en `api`
(rangos privados, ajustable con `CONTECFLOW_PROXY_CIDRS`) y arranca uvicorn con
`--no-proxy-headers` para que haya una sola política. Detrás de otro proxy hay
que fijar las dos variables (o los ajustes globales del mismo nombre).
`/ready`, `/status`, `/status/page.js`, `/status/embed.js` y `/widget/ticket.js`
también pasan a la API; `/metrics` no (Prometheus lo lee en `api:8000`).

`tests/test_docker_stack.py` fija estas invariantes. **Aviso honesto:** valida la
definición del stack, no que levante. Un `docker compose --profile app up` en un
host con Docker sigue siendo imprescindible antes de publicar.

## 9. Módulos funcionales
### 9.1 Proyectos y delivery
- Proyectos, fases, miembros
- Tareas, dependencias, kanban
- Epics, sprints, planificación
- Baselines y métricas de seguimiento
- Plantillas: la administración queda centralizada en `/project-templates` (creación completa desde cero incluyendo fases, tareas, riesgos y entregables; instanciación de proyectos desde plantilla).
- Workflows por proyecto: estados de workflow propios si existen; si no, estados base por defecto. `DELETE /api/v1/project-workflows/{project_id}/reset` restablece a Scrum estándar.
- Issue Types: ruta canónica `/api/v1/issue-types/{project_id}` (incluyendo `/init`).
- State machine de tareas: `cancelled` es terminal (no se puede salir); `todo → in_review` es inválida (requiere pasar por `in_progress` primero). El grafo completo está en `_TASK_VALID_TRANSITIONS` (`task_service.py`).

### 9.2 Tiempo y recursos
- Imputaciones y timer
- Timesheets y aprobaciones
- Capacity planning y scheduler
- Ausencias, skills, carga y burnout

Reglas funcionales:
- Cronómetro: permite cancelar la sesión sin guardar, cambiar la tarea final antes de imputar y forzar una imputación duplicada cuando ya existe otra para la misma tarea y fecha. Si se fuerza, se genera notificación in-app al manager responsable.
- Unicidad usuario+tarea+fecha se controla desde la lógica de negocio (no índice SQL), permitiendo únicamente los duplicados forzados desde el cronómetro.
- Las imputaciones duplicadas forzadas nunca sustituyen la anterior: se almacenan como registros adicionales y sus horas se acumulan en los totales semanales.
- `POST /api/v1/imputations/{imputation_id}/reject` permite a managers rechazar una imputación forzada sin borrar histórico (además de `approve`).
- `sync_timesheet_from_imputations_flow` siempre actualiza `total_hours`, `billable_hours` y `total_cost` independientemente del estado. Cuando un timesheet `approved` recibe nuevas imputaciones no aprobadas, vuelve automáticamente a `draft`.
- Mutaciones de imputaciones (crear, cerrar cronómetro, editar, borrar) sincronizan inmediatamente el timesheet semanal y, si estaba aprobado y cambia, invalidan la aprobación.
- Listado y lectura de imputaciones cargan `user`, `task` y `project` con `joinedload` para evitar N+1.
- Frontend del cronómetro **no** decide elegibilidad por `user.hourly_rate` del contexto de sesión (`/auth/me` usa `UserPublic` y no transporta tarifa). La validación efectiva de tarifa vive en backend al iniciar/detener.
- El timer activo devuelve y renderiza `project_name` y `task_name`; los UUID solo como fallback si faltan.
- El reloj superior y el widget compacto comparten la query global `timer-current`; cualquier `start/pause/resume/stop` actualiza esa cache para mantener consistencia entre TimerPage, widget y topbar.
- Ante `409` al detener cronómetro por imputación duplicada, la UI requiere consentimiento explícito (check en modal). No hay reintento forzado automático.
- TimerPage filtra el selector de tarea por `assigned_to_me: true`, igual que el formulario de inicio y que ImputarPage.
- En `/imputar`, los valores diarios y total semanal se formatean con máximo 2 decimales.
- La marca de facturable es editable al crear y al editar; las filas muestran badge cuando son facturables.

### 9.3 Finanzas
- Facturas y líneas
- Gastos
- Revenue recognition
- Rentabilidad
- Tipos de cambio

Endpoints relevantes:
- `POST /api/v1/invoices` crea facturas manualmente con líneas, `tax_rate` y datos del cliente. Calcula `subtotal`, `tax_amount` y `total`; genera número secuencial anual `INV-YYYY-NNN`.
- `GET /api/v1/invoices/{id}/pdf` devuelve PDF válido (ReportLab) con cabecera `%PDF`, `content-type: application/pdf` y `content-disposition: attachment; filename=factura_NNN.pdf`. Empleados y subcontratistas reciben 403.

### 9.4 CRM y clientes
- Clientes y contactos
- Pipeline comercial
- Contratos
- Portal cliente

### 9.5 Service Desk ITSM
Manual completo, de uso y de operación: [docs/SERVICE_DESK.md](docs/SERVICE_DESK.md).
- Tickets con avisos en cada paso (campana, correo y webhooks) y SLA con
  calendario por política, aviso de riesgo e incumplimiento, y escalado
- Correo entrante con hilo (IMAP, Microsoft 365 o pasarela), SMS firmado
- Catálogo con aprobación; tiempo de ticket a partes y factura
- Cambios con CAB, calendario, congelaciones y versiones
- Alertas de monitorización a incidencias y guardias
- Base de conocimiento con revisión, desvío en el portal y documentos de contecmind
- Problemas y KEDB, CMDB y topología, página de estado por organización

### 9.6 BI
- Dashboards
- Query builder
- Forecasting
- Anomalías
- ETL connectors
- Colaboración en dashboards

Reglas:
- El panel "Mi Trabajo" muestra métricas personales del usuario autenticado; no reutiliza KPIs globales de dirección para tareas, ausencias, gastos o aprobaciones.
- Las métricas de tendencia de horas devuelven datos tanto en SQLite local como en PostgreSQL.
- La variación mensual de horas suaviza el porcentaje cuando el mes base es demasiado pequeño.

### 9.7 IA
- NexusAssist
- Motor semántico
- Gobierno de IA
- Proveedores IA multi-tenant

## 10. Configuración por organización (org-defaults)
Valores por defecto centralizados en `app/core/config.py` (sobrescribibles por variables de entorno):
- `DEFAULT_CURRENCY = "EUR"`
- `DEFAULT_TIMEZONE = "Europe/Madrid"`
- `DEFAULT_LANGUAGE = "es"`
- `DEFAULT_WORKING_HOURS_PER_DAY = 8.0`
- `DEFAULT_WEEKLY_CAPACITY_HOURS = 40.0`
- `DEFAULT_VACATION_DAYS_PER_YEAR = 23`
- `DEFAULT_TAX_RATE = 21.0`

Endpoint backend: `GET /api/v1/settings/org-defaults` devuelve los valores actuales de la organización para consumo del frontend.

Hook frontend: `useOrgSettings` (`frontend/src/hooks/useOrgSettings.ts`) — TanStack Query con `staleTime` de 5min y fallback a defaults.

## 11. Estándares UI
Guía de diseño completa —tokens, temas con su contraste medido, componentes,
patrones, idiomas, accesibilidad y lo que no se debe copiar—, pensada también
para las otras soluciones: [docs/GUIA_DE_DISENO.md](docs/GUIA_DE_DISENO.md).

### Apariencia y accesibilidad (para quien usa la aplicación)
Se cambia en **Perfil → Apariencia**:
- **Tema:** Freight Pro (por defecto), Oscuro clásico, Midnight, Slate, Claro,
  Alto contraste o Sistema (sigue al sistema operativo). Todos se leen bien:
  el texto cumple el contraste mínimo de accesibilidad (WCAG AA) en los seis.
- **Color de acento:** el de los botones principales y lo seleccionado. Por
  defecto, *Acento del tema* (cada tema trae el suyo: dorado en Freight, azul
  en Oscuro…); también se puede elegir uno. El texto de encima se pone blanco
  o negro solo, el que se lea mejor con el color elegido.
- **Densidad:** *Compacta* reduce un punto la letra y el margen de la página
  para ver más a la vez; *Confortable* los aumenta para leer mejor.

Con el teclado: `Tab` recorre la pantalla y un contorno del color de acento
marca dónde se está (con el ratón no aparece). En una fila de pestañas, las
flechas cambian de pestaña, e `Inicio` y `Fin` van a la primera y la última.
Los avisos que salen abajo a la derecha los lee también el lector de
pantalla; los errores, en cuanto aparecen.

Las fechas salen en el idioma de la interfaz: `02/11/2026` en español,
`11/02/2026` en inglés y `2026/11/02` en chino. Quedan pantallas que todavía
las escriben en formato español (véase la guía de diseño, apartado 15).

### Modales y drawers
- Contenedor `position: fixed` (drawer: `top: 12, right: 12`; modal centrado: `inset: 0`).
- Altura por contenido; si excede el viewport, el cuerpo interno scrollea con `flex: 1; overflow-y: auto`. Cabecera y footer permanecen visibles (`flex-shrink: 0`).
- Ningún ancestro (`.page-content`, `PageShell`, etc.) debe aplicar `transform`, `filter`, `perspective` o `will-change` persistentes — rompen `position: fixed` al crear containing block. La animación `fadeUp` en `.page-content` se aplica sin `forwards`.
- Backdrop `position: fixed; inset: 0` con click-outside para cerrar.
- Margen exterior: 12 px (drawer) o `padding: 40px 24px` en el wrapper (modal centrado).

### Panel lateral de tareas
- Mantener padding vertical estándar para evitar recorte visual del contenido en la parte superior.

### Inbox
- El contador de la pestaña "Notificaciones" usa la misma fuente que la lista (`/enterprise/notifications` `unread_count`) para evitar desajustes entre badge y contenido.

### Externos como internos (16-11-2026)
- Rol `subcontractor`: menú Mi día, Tareas, Tiempo, Ausencias, Service desk (solo cola), Mis equipos y licencias, Bandeja; aterriza en `/work-dashboard`. Nada de gestión.
- Personas: marca «Externo · proveedor» (`MarcaExterno`, campo `external_company`) en `UserSelect`, Recursos y equipos de proyecto. Alta de externos desde Recursos › Nuevo externo (proveedor, responsable interno obligatorio, con o sin acceso, fin de acceso).
- Subcontratistas: asignación con persona, tarifa, papel y dedicación (crea el miembro del proyecto) y «Terminar asignación»; consumo con aviso por umbral (`EXTERNOS_UMBRAL_CONSUMO_PCT`); parte manual solo para personas sin acceso; conciliación de facturas contra horas imputadas. Detalle en README › Roles and permissions.

### Campana de avisos (16-11-2026)
- **Operadores** (barra superior, `CampanaDeAvisos`): número = «Sin leer» de la bandeja (avisos sin leer + alertas sin leer para admin/pm/hr), con las mismas claves de react-query que la pestaña y la bandeja. Contador: `GET /enterprise/notifications/unread-count` (COUNT acotado al usuario); si responde 404/405 (backend sin reiniciar) cae al `unread_count` de la lista. Panel con los últimos 8, «Marcar todas» (avisos y alertas) y «Ver todas» → `/inbox?tab=notifications` (la pestaña de /inbox sale de la URL).
- **Tiempo real**: un único WebSocket `/ws/notifications` por pestaña (`hooks/useAvisosEnVivo.ts`), compartido por campana y bandeja; cada mensaje `notifications`/`notification_push` invalida los contadores. Sin socket, sondeo cada `NOTIFICATIONS_POLL_MS`.
- **Portal** (`CampanaDelPortal`, sección `notifications`): avisos del cliente en `CollaborationNotification` (`client_user_id`). Nuevos: `GET /portal/collaboration/notifications/unread-count`, `POST …/{id}/read` (lo de otro cliente es 404 `notificacion_no_encontrada`); la lista acepta `limit` y devuelve `payload` filtrado (`tipo`, `seccion`, `ticket_id`). Se crean avisos al cliente solicitante con cada aviso de ticket que ya recibía por correo (`ticket_event_processor`) y con los mensajes del equipo al proyecto (`avisos_del_portal.py`). El WS del portal incluye `notifications_unread`.
- **Sin emojis**: los títulos de `Notification` y `CollaborationNotification` se guardan sin emojis (`app/core/sin_emojis.py`, validador del modelo); la interfaz pinta iconos lucide por tipo (`components/avisos/iconosDeAviso.tsx`).

### Filtros con pills
- En pantallas con filtros rápidos por URL (ej. `tasks?mine=1&overdue=1&status=open`), mostrar pills visibles con acción de quitar individual y botón de limpieza rápida.
- Listados con filtros (Timesheets, etc.) muestran contador `filtrado/total`, botón `Limpiar` y estado vacío "Sin resultados".

### Exportar a Excel global
- `PageHeader` exporta cualquier tabla HTML, grid tabular o lista de cards visible mediante el botón "📊 Exportar Excel" (formato `.xls`).
- Pantallas con lista exportable real: usar `exportTargetSelector` + `data-export-table="<nombre>"` para selección determinista (Tasks, Projects, Invoices, Approvals, Service Desk, etc.).
- Pantallas sin lista exportable real (dashboards, Gantt/Kanban, herramientas, formularios, settings, integraciones): `showListExport={false}`.
- Fallback para listas tipo tarjetas: cada card como fila en columna "Detalle".
- Estado vacío con cabeceras visibles produce `.xls` con cabeceras solas.

## 12. Seguridad y compliance

### Las cuatro capas de autorización

Para saber si un endpoint está protegido hay que mirar las cuatro. Están
ordenadas de la más difícil de olvidar a la más discrecional:

| Capa | Qué protege | Fallo | Se puede olvidar |
|---|---|---|---|
| Aislamiento de tenant | Que un cliente no vea datos de otro | **cerrado** | No: es automático |
| RBAC | Qué puede hacer cada rol | cerrado | Sí: hay que escribirlo |
| Matriz GRC | Restricciones que configura el cliente | abierto (aditivo) | No: es automático |
| ABAC | Política de grano fino opcional | abierto | No: es automático |

**1. Aislamiento entre tenants** — `app/db/session.py::TenantSession`.
Filtra toda consulta ORM por organización, en `query()` (SA 1.x) y en `execute()`
(SA 2.0). Cubre los 434 modelos con organización (423 por `organization_id`, 11 por `org_id`) de 435 (medido el 16-11-2026 importando `app.models`; ya no queda ninguno que dependa solo de `project_id`/`user_id`). Es **fail-closed**: si un modelo no se puede
aislar, la consulta lanza `TenantIsolationError` en lugar de ejecutarse sin
filtro. La única exención (`Organization`, que ES el tenant) se declara en el
propio modelo con `_tenant_exempt = True` y sus rutas llevan guarda manual.
La tercera capa (`do_orm_execute`, la que cubre cargas que se cuelan por las otras)
también filtra los 11 de `org_id` desde 2026-11b; antes solo los de `organization_id`.

Fuera de la petición (worker, webhooks, bots) no hay filtro hasta que alguien
publica la empresa: `en_cada_organizacion` (solo empresas **activas**, también
cuando se le pasa la lista), `como_organizacion` por fila, o
`publicar_contexto_de_tenant` por sujeto. Revisión 2026-11b
(`tests/test_multitenant_revision_2026_11b.py`): la empresa de un evento saliente
es la explícita, la de la sesión o la del proyecto, nunca la de ficha de un
superadmin; claves de API, tokens de aplicación y el agente en segundo plano
trabajan en la empresa en la que se crearon (no en la de ficha del dueño); lo que
se hace «entrando como» queda auditado con `impersonated_by`; webhooks entrantes
(CAB, Jira, monitorización) rechazan empresas desactivadas y sellan su empresa.

**2. RBAC** — `app/core/deps.py`. `require_admin`, `require_any_manager`,
`require_superadmin`… en la firma del endpoint, o comprobaciones de rol dentro
del servicio. Las dos formas se usan; `tests/test_abac_coverage.py` mantiene el
inventario de las rutas que sólo la tienen en el servicio.

Ojo con la distinción que causó el incidente P0-1 de la auditoría 2026-08:
`require_admin` es el administrador **de un cliente**, no de la plataforma. Todo
lo que opere entre organizaciones necesita `require_superadmin`.

**3. Matriz de permisos GRC** — `app/core/grc_enforce.py`.
Lo que un administrador prohíbe en la pantalla de GRC queda prohibido. Es
**denegación aditiva**: una fila sólo puede quitar permiso, nunca darlo, así que
no puede escalar privilegios por encima del RBAC. Sin fila, deciden las demás
capas.

Módulo y acción se **derivan de la ruta** (`app/core/grc_catalog.py`): el módulo
del primer segmento del path, la acción del método HTTP matizado por el path para
distinguir `aprobar` y `exportar`. No hay lista que mantener — un dominio nuevo
entra en la matriz el día que se añade su primera ruta. Cobertura: todos los
dominios no exentos de la API (111 medidos en la revisión GRC 2026-11b). Las
exenciones son propias de GRC (`GRC_EXEMPT_PREFIXES`: login, portal de cliente,
SCIM, WebSocket, las subrutas públicas de webhooks y formularios, catálogos de
UI) y no la lista de ABAC, que exime también rutas con usuario. Las casillas
globales de un módulo cuya ruta se borra se retiran solas, y la pantalla pinta
los módulos que da la API.

**4. ABAC** — `app/core/abac_dependency.py` y `abac_enforce.py`.
Política de grano fino que un cliente activa si quiere. Es **fail-open**: sin
políticas activas no restringe nada, y por diseño. `enforce_abac()` NO es un
control de autorización por sí solo, aunque el nombre lo sugiera.

### Qué NO protege qué

Errores que la auditoría 2026-08 encontró y que conviene no repetir:

- `enforce_abac()` no aísla tenants. Es fail-open. Un endpoint cuyo único control
  fuera esa llamada estaría sin proteger.
- La matriz GRC no concede permisos, sólo los quita.
- Un middleware de Starlette no puede leer el usuario autenticado: las
  dependencias de FastAPI se resuelven después. `ABACMiddleware` se borró por eso
  — comprobaba un `request.state.user` que nadie poblaba nunca.

### Otras capacidades activas
- JWT, refresh y MFA (TOTP + WebAuthn), forzado también en SSO
- SSO OIDC con verificación de firma contra JWKS, PKCE S256, `state` con HMAC de
  un solo uso y verificación de `nonce`
- Rate limiting: 128 decoradores `@limiter.limit` (16-11-2026) y `RATE_LIMIT_DEFAULT` en el resto (por ruta y usuario; sin sesión, por IP), bloqueo por intentos en
  login, Redis obligatorio en producción
- Confianza en proxies (`app/core/network.py`): `X-Forwarded-For` (recorrido de derecha a izquierda), `X-Real-IP`, `X-Forwarded-Host` y `X-Forwarded-Proto` (`EsquemaDelProxyMiddleware`) solo cuentan si `TRUST_PROXY_HEADERS` está activo y la IP que conecta está en `TRUSTED_PROXY_CIDRS`. Ambos son también ajustes de plataforma (fila global, solo superadmin, caché de 5 min). Ver §8bis, nginx
- Mínimo privilegio dentro de la empresa: personas y ajustes con una sola regla (`app/services/politica_de_visibilidad.py`: el subcontratado solo ve la ficha mínima de la gente de sus proyectos y 404 para el resto; el empleado, sin contacto ajeno; tarifas solo admin y RRHH; cada ajuste con su `Audiencia` `SESION`/`INTERNA`/`ADMIN`); herramientas del asistente (chat, agente y MCP) con la guarda de rol y la matriz GRC de su endpoint REST equivalente (`app/services/ai_chat/tool_execution/politica.py::POLITICAS`; sin política, no se ejecuta). Detalle en §2, «Segunda auditoría 2026-11»
- CSRF en dos capas: Origin/Referer siempre + double-submit opcional
- Cifrado de secretos de integraciones
- Validación de subidas unificada: extensión, MIME, bytes mágicos y coherencia
  entre ellos, con lectura acotada por perfil (`app/core/uploads.py`)
- Auditoría de eventos y SCIM

Puntos de entrada:
- `app/core/security.py` — tokens, hashing, política de contraseñas
- `app/core/deps.py` — RBAC (incluido `require_superadmin`)
- `app/core/tenancy.py` — guardas para un `org_id` que llega del cliente
- `app/db/session.py` — aislamiento automático de tenant
- `app/core/grc_enforce.py` / `grc_catalog.py` — matriz GRC
- `app/core/abac_dependency.py` / `abac_enforce.py` — ABAC
- `app/core/uploads.py` — seguridad de subidas
- `app/api/v1/endpoints/grc.py` — API de GRC y SoD

### Segregación de Funciones (SoD)
La regla nuclear se aplica en la bandeja (`app/services/approval_engine/requests.py`)
y en las rutas de aprobación directa (`approval_engine._base.exigir_que_no_sea_suyo`:
ausencias, imputaciones, documentos, hitos, traspasos de presupuesto, cambios):
el solicitante no puede aprobar su propia solicitud (403). Está escrita en el
código, no sale de la tabla `SodRule`.

La infracción se registra con un único registrador
(`grc_sod.record_self_approval_violation_for_request`), en la empresa de la
regla, traduciendo la entidad a su módulo GRC (`expense` → `expenses`,
`leave`/`absence` → `absences`). Limitación conocida: sólo se consultan reglas
con el mismo módulo a los dos lados y `aprobar` en el segundo; una regla entre
módulos distintos ("no puede crear facturas y aprobar gastos") sólo la ve
`/grc/sod-check`. Ver `tests/test_grc_coverage.py`.

### Revisión GRC (16-11-2026)
Tests: `tests/test_revision_grc_2026_11_16.py` y `tests/test_i18n_codigos_del_backend.py`.
- **Reglas SoD** (`schemas/grc.py`, `grc_service.validar_regla_sod`): módulo del catálogo derivado de las rutas, acción del vocabulario `GRC_ACTIONS`, roles de la matriz, riesgo `critical|high|medium|low`, dos operaciones distintas; el flujo de mitigación debe ser de la empresa (404). `PATCH` con esquema (`SodRuleUpdate`): ya guarda módulos y acciones (antes los ignoraba) y sólo revalida lo que cambia. La regla nace con `organization_id` explícito. `/sod-check` lee la matriz una vez (antes 2 consultas por regla y rol) y devuelve `not_evaluable_rule_ids`: reglas cuyas operaciones no son casillas de la matriz (p. ej. «aprobar» facturas, gastos, horas, ausencias o presupuestos: no tienen ruta propia; sólo las vigila el registro de autoaprobaciones). Resolver una violación ya resuelta: 409. `GET /grc/permissions` devuelve `actions`.
- **Marcos y evidencias** (`app/core/marcos_de_cumplimiento.py`, una sola fuente): ISO 27001:2022 (`A.9.2` de 2013 pasa a `A.5.18`; las evidencias antiguas cuentan por `ALIAS`, sin migración), SOC 2 con CC6.3 (lo citaba un paquete y no estaba). La evidencia exige un control del marco y un tipo cerrado; `artifact_hash` ya no es el SHA-256 del texto de la URI: se guarda el `artifact_sha256` que manda quien tiene el fichero. `controls/status` cruza la evidencia con el informe medido (`measured`): un control medido en «attention» no pasa por tener evidencias. Nuevo `GET /governance/compliance/frameworks` y pestaña «Marcos y evidencias» en GRC (la API no tenía pantalla). `PATCH /governance/config/{module}` exige booleano.
- **RGPD** (`cab_service/gdpr.py`): tipo validado (enum), persona o correo obligatorio, persona de la empresa (404), plazo `COMPLIANCE_GDPR_MAX_DAYS` (era 30 fijo), lectura y proceso acotados a la empresa. «Acceso» (art. 15) entrega la misma copia que la portabilidad, con imputaciones y tickets (antes se completaba sin nada, y la portabilidad era un recuento con «solicite el fichero al administrador»); `GET /gdpr/requests/{id}/export` la descarga; `POST /gdpr/requests/{id}/reject` (rechazo motivado). El informe (`gdpr_requests`) cuenta también las solicitudes vencidas de BI (`bi_overdue`).
- **Permisos por proyecto**: `permisos_de_proyecto.decidir` devuelve un código (`MOTIVOS`); el mensaje sólo lo pone el 403. El explicador de accesos usaba la frase en castellano como clave de traducción.
- **Pantalla**: claves de caché propias para retención y bloqueo legal (`['retention']`/`['legal-holds']` eran también las del chat, con otra forma de datos); al cambiar el tipo de un bloqueo se corrige el campo; confirmación antes de «Aplicar ya» y de levantar un bloqueo; riesgos, severidades, eventos de auditoría, campos de bloqueo, roles y módulos traducidos; estados RGPD traducidos con «Rechazar» y «Descargar copia». El test de i18n cruza esos códigos con los tres idiomas.
- **Sin arreglar**: `session_revocation` del informe da «pass» por la existencia de la función (lo garantizan los tests, no un dato); la columna «medido» del informe muestra las claves técnicas; hay dos registros de solicitudes RGPD (`gdpr_requests` y `bi.gdpr.dsr` en `app_settings`) que deberían unificarse.

### Rotación de claves
- `bash scripts/rotate_keys.sh` (genera `SECRET_KEY` nueva, guarda la anterior en `SECRET_KEY_PREVIOUS` y recifra con `scripts/reencrypt_secrets.py`; `--check` cuenta lo pendiente). Detalle: README, «Technical guide → 7.5».
- La rotación del anillo JWT y el recifrado de secretos de integración van solos (tarea `run-key-rotation` de beat).

### Verificación local
Este proyecto no usa CI/CD ni hooks de git por decisión de diseño (`.git/hooks`
solo tiene los `.sample`): las comprobaciones se lanzan a mano. Los gates del
backend están reunidos en `scripts/ci_local.sh`; los del frontend son los scripts
de `frontend/package.json` (`lint`, `typecheck`, `check:i18n*`, `test`…):

```bash
./scripts/ci_local.sh          # todo
./scripts/ci_local.sh --fast   # sin pytest ni informativos (~2 min)
./scripts/ci_local.sh --info   # sólo los informativos
```

Distingue gates **bloqueantes** (verdes hoy; si uno falla es una regresión que
acabas de introducir) de **informativos** (deuda medida y documentada). El
`--max-warnings` de eslint está fijado en la línea base medida (1966 en
`scripts/ci_local.sh` a 16-11-2026): al reducir deuda, bajar ese número; nunca
subirlo. `ruff` no está en `requirements.txt`: el primer gate bloqueante falla
hasta instalarlo (`pip install ruff`).

## 13. Testing
### Backend
- pytest con fixtures comunes en `tests/conftest.py` (SQLite en memoria, `TESTING=1`); 465 ficheros `test_*.py` (16-11-2026)
- `make test` (= `pytest tests/ -n auto`), `make test-serial`, `make test-module M=test_okrs`
- `pytest -q tests/test_auth.py`

### Frontend
En `frontend/`:
- `npm run test` (Vitest, jsdom; `src/**/*.test.{js,jsx,ts,tsx}`: 55 ficheros a 16-11-2026)
- `npm run lint`, `npm run typecheck`, `npm run check:i18n` y el resto de `check:i18n:*`
- `npm run build`
- `npm run test:e2e` llama a `playwright test`, pero el frontend no tiene `playwright.config.*` ni `*.spec.ts`: el E2E que funciona es el de Python (`tests_e2e/`)

### E2E
- `tests_e2e/`
- `scripts/run-ui-tests-linux-mac.sh`

Notas:
- La ruta `/approvals` tiene smoke E2E dedicado para validar CRUD real de workflows y pasos desde la UI autenticada, con limpieza del dato de prueba al final.
- La suite `tests_e2e/` depende de `playwright` y `pytest-playwright` en Python; tras instalar dependencias puede requerir `playwright install chromium`.

## 14. Operación
### Observabilidad
- Logs de aplicación
- Sentry y OpenTelemetry si están habilitados; métricas Prometheus en `/metrics` (`METRICS_ENABLED`) y perfil `observability` en el compose

### Jobs periódicos
Definidos en `app/worker.py` (`celery_app.conf.beat_schedule`: 42 entradas, 46 tareas, a 16-11-2026; tabla completa en el README, «Technical guide → 8.2»):
- Jobs de alertas
- Informes programados
- Jobs BI/ETL
- Jobs IA
- Jobs de service desk
- Automatizaciones, temporizadores BPMN, retención, purgas, tipos de cambio, ausencias, resumen diario de avisos

Las horas son de `DEFAULT_TIMEZONE`. Un solo calendario: Celery beat (compose,
`setup.sh`, `setup.bat`, con `ENABLE_APSCHEDULER=0 ENABLE_CELERY_BEAT=1`) o, si
no hay beat, APScheduler dentro de la API, que replica el `beat_schedule` entero
(`app.main._replicar_celery_beat`). Con los dos activos la API no arranca.

Notas:
- El cierre de APScheduler en el shutdown de la API es idempotente: solo intenta shutdown si el scheduler sigue en estado `running`.

## 15. Integraciones
Integraciones soportadas según configuración:
- Jira
- Microsoft 365
- GitHub / GitLab
- Salesforce
- Stripe
- Twilio
- AWS S3/KMS
- Slack y Microsoft Teams (bots y comandos)
- DocuSign y Adobe Sign

Secretos de entrada: Jira usa un secreto **por organización** (`POST /api/v1/jira/webhook-secret`; el `JIRA_WEBHOOK_SECRET` global ya no autentica); Stripe, `STRIPE_WEBHOOK_SECRET` (sin él el webhook responde 503); correo entrante, `INBOUND_EMAIL_SECRET` o la credencial `webhooks.inbound_email_secret` de la organización (cabecera `X-Contecflow-Email-Secret` en `POST /api/v1/sd/inbound-email`, o `X-Inbound-Secret` en `POST /api/v1/sd/multichannel/inbound/email`; obligatorio en staging/producción); Slack/Teams se vinculan a una empresa con los ajustes `SLACK_TEAM_ID`/`TEAMS_TENANT_ID`; Twilio, con los números de la empresa (`TWILIO_PHONE_NUMBERS`). Pasos de despliegue: [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md).

### E-firma (DocuSign y Adobe Sign)
Configuración accesible desde Settings → Sistema → E-firma (rol admin).

Backend:
- `GET /esign/config` y `PATCH /esign/config` persisten credenciales en `app_settings` (KV store, claves `esign.*`). Sin migración nueva.
- Secretos (`docusign_secret_key`, `adobe_sign_client_secret`) se enmascaran como `"***"` en GET; PATCH ignora el valor `"***"` para no sobreescribir.
- `GET /esign/summary/stats` consulta primero claves DB y hace fallback a env vars.

Frontend:
- `esignApi.getConfig` / `saveConfig` (`frontend/src/services/api/_core.ts`).
- `ESignSettingsSection`: tarjeta por proveedor con badge configurado/no configurado, campos secretos tipo password y botón Guardar.

### Documentos
- `HEAD /api/v1/documents/file/{file_key}` en almacenamiento local devuelve metadatos (`Content-Type`, `Content-Length`, `Content-Disposition`) sin descargar el fichero, evitando warnings `405` en comprobaciones previas del navegador.

## 16. Troubleshooting rápido
### Backend no arranca
- Verificar entorno virtual activo
- Verificar dependencias instaladas
- Verificar `DATABASE_URL`

### Migraciones fallan
- `alembic current`
- `alembic upgrade head`
- Revisar tabla `alembic_version`

### Worker falla
- Verificar `REDIS_URL`
- Verificar Redis activo
- Revisar logs worker/beat

### Frontend build falla
- `npm install`
- Revisar `frontend/.env`
- `npm run build`

### Seed falla
- Ejecutar migraciones primero
- Revisar el traceback de `python -m app.db.seed` (el que usa `setup.sh demo`); `scripts/seed_full_data.py` es otro generador, más pesado
- Las semillas y `scripts/reset_to_admin_only.py` se niegan (salida 2) si `ENVIRONMENT` no es de desarrollo o pruebas

Más síntomas con causa medida: README, «Technical guide → 12. Troubleshooting».

## 17. Política de limpieza del repositorio
No versionar:
- venv y entornos locales
- node_modules y dist
- caches
- archivos temporales de SQLite
- reportes temporales generados localmente
- archivos del sistema operativo
- `.env.*` (`.env.local`, `.env.produccion`), salvo `.env.example`

Controlado por `.gitignore`. El `.env` **sí** va versionado a propósito
(repositorio privado; una máquina nueva arranca con la misma configuración):
quien lee el repositorio tiene los secretos de desarrollo, así que los de
producción nunca van en él.

## 18. Mantenimiento de esta documentación
Reglas:
- `DOCS.md` refleja el estado actual.
- Evitar históricos largos de cambios internos.
- Evitar referencias a documentos retirados.
- Consolidar periódicamente para mantener claridad.

## 19. Motor de flujos de aprobación documental
### Descripción
Los documentos que requieren aprobación (`requires_approval=True`) se gestionan a través del motor multi-nivel (`approval_engine`), el mismo que usan partes de horas, gastos, ausencias, cambios, facturas y presupuestos (ver §22 y el README, «Approval Inbox»). No existe entidad de compras.

### Cómo funciona
1. Al subir un documento con `requires_approval=True`, el sistema busca el flujo de su categoría (`documents_service._auto_create_approval_request` → `find_document_workflow`).
2. Búsqueda (`_base.find_default_workflow`): primero un flujo activo `entity_type=document` con `trigger_conditions={"category":"<cat>"}`, luego el genérico `entity_type=document` + `is_default=True`. No usa `elegir_flujo` ni el motor de políticas.
3. Si encuentra flujo con pasos, crea un `ApprovalRequest`, lo enlaza en `Document.approval_request_id` y notifica al primer aprobador.
4. «Enviar para aprobación» (`POST /documents/{id}/submit-approval`, acceso `editor`) repite esa búsqueda; sin flujo responde 422. Tras un rechazo o cancelación se puede volver a enviar; con una solicitud activa, 409.
5. Cada decisión avanza el flujo paso a paso. Al completarse, `Document.approval_status` se actualiza automáticamente. Sin solicitud enlazada, `POST /documents/{id}/approve` (acceso `admin` del documento) fija el estado directamente.

### Configuración por categoría
En Settings → Approval Workflows: crear flujo con `entity_type=document` y `trigger_conditions={"category":"legal"}`. El motor selecciona el flujo más específico automáticamente.

## 20. Gobierno de flujos: separación operación vs configuración
Objetivo:
- Evitar confusión entre "aprobar solicitudes" y "definir reglas de flujo".
- Centralizar toda definición en Configuración.

Mapa funcional:
- Approval Inbox (`/approvals`): bandeja operativa diaria para aprobar/rechazar pendientes.
- Approval Flows (Config) (`/settings/approval-workflows`): definición de flujos multi-nivel (pasos, roles, tiempos, reglas). La pantalla la abren admin, pm y team_lead; crear, editar, publicar, clonar, borrar, simular y gestionar grupos es solo admin (`require_admin`); la analítica, cualquier responsable.
- Políticas y reglas (`/settings/policies`): las reglas de negocio (bloquear, pedir niveles, avisar, exigir documentos, cupos) de gastos y ausencias (§22 bis–quater).
- Project Issue Flows (Config) (`/settings/project-workflows`): definición de estados y transiciones de tareas/incidencias por proyecto.

Compatibilidad de rutas:
- `/workflows` redirige a `/settings/project-workflows`.
- `/settings/workflows` redirige a `/settings/project-workflows`.

Reglas de producto:
- Ninguna pantalla operativa debe mezclar decisiones en curso con edición de definiciones.
- Toda definición de comportamiento de flujo vive bajo Configuración con naming explícito.

## 21. Approval Flows (Config) — capacidades enterprise
URL principal: `/settings/approval-workflows`

Capacidades:
- Templates: biblioteca de plantillas listas para crear flujos base (legal, engineering, expense high-amount) y opción de crear flujo completo desde cero (definición + pasos) desde la misma pestaña.
- Simulator: simulación de selección de flujo y ruta de pasos antes de publicar.
- Validate: valida calidad del flujo (pasos, orden, aprobadores requeridos, consistencia).
- Publish: publicación segura (solo publica si la validación no tiene errores bloqueantes; si no, 422 con los problemas). Publicar = activar el flujo (`is_active`).
- Clone Version: clona un flujo con sus pasos como nueva versión inactiva y no predeterminada, sin impactar el activo.
- Diseñador gráfico: el diagrama se valida y se compila a pasos (`GET/PUT /workflows/{id}/diagram`, `POST /workflows/{id}/diagram/check`; reglas en §22 bis, punto 4).
- Bottlenecks: analítica de cuellos de botella por paso (tiempo medio, rechazo, pendientes, riesgo de SLA, score).
  - Dashboard ejecutivo con KPIs globales de riesgo, top workflows con mayor riesgo, tendencia semanal de rechazo y recomendaciones priorizadas (high/medium).

## 22. Approval Engine v2 Enterprise
### Tipos de entidad soportados
El diseñador ofrece `document`, `timesheet`, `expense`, `change_request`, `milestone`, `purchase`, `invoice`, `contract`, `budget`, `budget_transfer`, `leave`, `deliverable`, `proposal`, `subcontractor`, `scope_change`, `hire`, `price_change` y `mcp_action` (`entity_type` es texto libre en el API). Abren solicitudes solas y reciben la decisión final: `document`, `mcp_action` y los tipos de `approval_engine/fuentes.py` (`expense`, `timesheet`, `leave`, `change_request`, `invoice`, `budget`, `budget_transfer`); el resto solo se abre a mano o por una automatización y la decisión no se aplica a ninguna entidad (detalle en el README, «Approval Inbox» → *Limitations*).

### Funcionalidades
- **Grupos de aprobadores** (`ApprovalGroup`): CRUD en `/approvals/groups`. Pasos con `approver_type=group` + `approver_group_id`. El motor valida pertenencia leyendo `member_ids`.
- **Quórum paralelo**: `parallel_quorum=True` + `required_approvals`. Varios aprobadores votan en paralelo; el paso avanza al alcanzar quórum. Prevención de doble-voto.
- **Condición de paso** (`step_condition`): JSON con reglas (`amount_gt`, `amount_lt`, `department`, `category`) o, en ramas del diseñador gráfico, `{"dominio", "arbol"}` evaluado por el motor de políticas. Si no cumple, se salta automáticamente; si no se puede evaluar, el paso cuenta como activo.
- **Adjunto obligatorio** (`requires_attachment`): la decisión debe incluir `attachment_url`, persistido en `ApprovalDecision`.
- **Recordatorio automático** (`reminder_hours`): el job horario vuelve a avisar a los aprobadores cada N horas mientras el paso siga pendiente.
- **Auto-aprobación** (`auto_approval_rules`): reglas JSON en el workflow; si la solicitud cumple, se auto-aprueba al crearla sin pasar por pasos manuales, salvo que una política haya añadido niveles o pasos.
- **Encadenamiento** (`chain_on_approval_workflow_id`): al aprobarse completamente, crea automáticamente nueva solicitud en el workflow encadenado.
- **SLA block** (`sla_block_on_breach`): se guarda y se edita en el formulario del flujo, pero ningún código lo aplica (no bloquea nada al superar el SLA).
- **Carga de aprobadores** (`/analytics/approver-load`): pendientes, tiempo medio de respuesta, tasa de rechazo, antigüedad media de lo pendiente y `load_score` = pendientes × 1,5 + horas medias de respuesta × 0,1 (sin tope); sobrecargados = 5 o más pendientes o 48 h o más de antigüedad media.
- **Pasos de informar y por nivel jerárquico** (`kind = inform`, `approver_type = manager_level`) y etapas en paralelo: ver §22 bis, punto 3.

### Tabs frontend
- **Grupos**: CRUD de grupos con selección de miembros.
- **Carga**: tabla por aprobador con score, badge de sobrecargado y selector de período.
- **Matriz**: grid entidad × flujo con flujos activos/default por tipo de entidad.

### APIs principales
- `GET /api/v1/approvals/workflow-templates`
- `POST /api/v1/approvals/workflows/from-template`
- `POST /api/v1/approvals/simulate`
- `GET /api/v1/approvals/workflows/{workflow_id}/validate`
- `POST /api/v1/approvals/workflows/{workflow_id}/publish`
- `POST /api/v1/approvals/workflows/{workflow_id}/clone-version`
- `GET /api/v1/approvals/analytics/bottlenecks?days=90` — respuesta con `summary`, `top_workflows`, `weekly_trend`, `recommendations`.
- `GET /api/v1/approvals/analytics/approver-load?days=90`
- `GET/POST /api/v1/approvals/groups`
- `GET/PATCH/DELETE /api/v1/approvals/groups/{id}`

Notas:
- `trigger_conditions` soporta reglas por categoría/departamento/importe (`amount_gt`, `amount_gte`, `amount_lt`, `amount_lte`), `project_id` y `policy_exceeded` (gastos). `elegir_flujo` toma el flujo activo más específico que encaje y, si ninguno, el predeterminado; el flujo de un tipo de ausencia manda sobre él; los documentos usan su propia búsqueda (§19).
- Diseño y ciclo de vida del motor (modelos, avance, vencimientos): `docs/APPROVAL_ENGINE.md`.
- El simulador no crea solicitudes reales; solo evalúa coincidencia y resolución de aprobadores.

## 22 bis. Motor de políticas, reglas y flujos (tarea #26, revisión 165)

Un solo motor para gastos, ausencias y los procesos que vengan. Reglas de arquitectura:

1. **El motor no conoce dominios.** Cada dominio se registra con `registrar(Dominio(...))`
   (`app/services/politicas/registro.py`, reexportado por `catalogo.py`, que carga `dominios/`) con su
   catálogo de campos tipados (`importe`, `numero`, `texto`, `enum`, `entidad`, `fecha`, `pais`, `ciudad`,
   `booleano`, `periodo`) y sus ganchos (`contexto`, `cargar`, `historicos`,
   `propietario`, `resumen`, `cumple_requisito`, `aplicar_campo`). Prohibido importar modelos de un
   dominio desde `motor.py`, `condiciones.py` o `resultados.py`. Ejemplo completo: `dominios/gastos.py`.
2. **Evaluar no tiene efectos.** `politicas.evaluar` es pura (la usan el simulador y los dominios);
   los efectos van aparte y los decide el dominio: `registrar_evaluacion`, `aplicar_campos`,
   `ejecutar_avisos` (lo llama la apertura de la solicitud). El simulador comprueba al final que la
   sesión no tiene nada pendiente de escribir y, si lo tuviera, deshace y responde 500.
3. **No hay un segundo motor de aprobaciones.** Lo que piden las políticas entra en `approval_engine`:
   `create_approval_request(..., politicas=resultado)` / `fuentes.abrir(..., evaluacion=ev)` añaden
   pasos a ESA solicitud (`approval_request_steps`, detrás de los del flujo); `approval_engine/pasos.py`
   mezcla pasos del flujo y de la solicitud (`pasos_de`) y es el único sitio que avanza una solicitud
   (`avanzar`): etapas por `step_order`, ramas en paralelo con votos por rama (`approval_decisions.step_ref`),
   pasos `kind = inform` que avisan y siguen, y `approver_type = manager_level` (N-ésimo responsable,
   `_base.responsable_de_nivel`). Quien añada otra vía de avance la escribe sobre `avanzar`.
4. **El diseñador gráfico compila, no ejecuta.** `approval_engine/diagrama.py` valida el grafo
   (un inicio, alcanzable, sin ciclos, condición con salidas sí/no, paralelo con una rama = un paso que
   llega al mismo «unir») y lo compila a `ApprovalStep`. Las condiciones de rama se guardan como
   `step_condition = {"dominio", "arbol"}` y las evalúa el motor de políticas sobre
   `approval_requests.contexto` (falla hacia «la rama está activa»).
5. **Lógica de tres valores.** Una condición que no se puede evaluar (sin tipo de cambio, sin fila de
   tabla, campo desconocido) es indeterminada: la regla no dispara y se añade un aviso. Nunca se
   inventa un tipo de cambio 1:1 (se usa `currency_rates_service.get_rate` y su inverso, no
   `resolve_rate`, que devuelve 1.0 si no encuentra).
6. **Combinación determinista** (`resultados.combinar`, documentada en su cabecera y en el README):
   bloqueo > niveles (máximo, no suma) > requisitos/avisos (unión) > auto-aprobar; `set_field` lo gana la
   política de mayor prioridad. Los resultados se recorren en orden (prioridad desc., nombre, id; reglas
   por orden), así que la misma entrada da siempre la misma salida.
7. **Caché.** `motor.publicadas` compila por (empresa, dominio) y comprueba en cada evaluación una firma
   barata (número y última modificación de políticas del dominio y de tablas de la empresa). Toda
   escritura de `servicio.py` llama a `motor.invalidar`. Una escritura nueva que toque políticas o tablas
   por otra vía tiene que actualizar `updated_at` y llamar a `invalidar`.
8. **Versionado.** Solo un borrador se edita; publicar retira la publicada anterior de la familia
   (`familia_id`); borrar una publicada la retira. El historial no se borra.
9. **Sin JSON a mano.** Ámbito, condiciones, resultados, bandas y diagrama se guardan como JSON y se
   editan SOLO desde `PoliticasPage` y `DisenadorDeFlujo`. Los ajustes van al grupo `politicas` del
   catálogo (`POLICY_*`, `app/core/config_groups/politicas_config.py`).
10. **Permisos.** Configurar: `require_admin` + matriz GRC (módulo `policies`) + `enforce_abac`
    (recurso `policy`). Explicación de una entidad: dueño, aprobador o admin (`servicio.explicaciones`).

Tests: `tests/test_motor_de_politicas.py` (moneda, bandas, fechas y grupos, conflictos, niveles en la
solicitud, paralelo e informar del diseñador, simulador sin efectos, aislamiento por empresa,
versiones y guardas).

## 22 ter. Gastos sobre el motor de políticas (tarea #27, revisión 166)

1. **Un solo camino de envío.** `expense_service.submit_expense_record` → `gastos_politicas.al_enviar`
   (evaluar; 422 si una política BLOQUEA o falta un requisito; `aplicar_campos`; `policy_flags` =
   resumen) → commit → `tras_enviar` (`registrar_evaluacion` + `fuentes.abrir(…, evaluacion=ev)` y
   enlaza la evaluación con su solicitud). No hay envío masivo, móvil ni por API aparte: todos llaman
   a `POST /expenses/my/{id}/submit`. `gastos_avanzados.antes_de_enviar`, `ExpensePolicy` y
   `/expenses/policies` ya no existen.
2. **Un exceso no bloquea.** Las bandas piden niveles (`add_approval_levels`), avisan o exigen; solo
   `block` da 422. Los niveles van detrás de los pasos del flujo (`pasos.anadir_por_politicas`: el
   primero es el nivel de responsable que el flujo aún no cubre). Sin flujo, `fuentes.abrir` abre la
   solicitud solo con los pasos de la política (`workflow_id` NULL; `requests.py` lo admite al decidir y
   en la bandeja). La auto-aprobación del flujo no salta niveles pedidos por una política, y
   `review_expense` da 409 mientras haya una solicitud pendiente con pasos de política.
3. **Campos calculados en el dominio** (`dominios/gastos.contexto`): por asistente, total del día (todas
   las categorías o la suya), total del viaje, tarifa por km, fin de semana, festivo (`holidays`; uno
   con `applies_to` = país solo cuenta en ese país), cliente y facturabilidad del proyecto, grado
   (`users.grade`). Los totales convierten cada gasto a la moneda de este al tipo de su fecha; sin tipo
   el campo queda vacío y la condición indeterminada (aviso), nunca 1:1. Grado y viaje son `enum`
   con `opciones_dinamicas` (los valores que existen).
4. **Kilometraje.** `aplicar_kilometraje` usa la tabla de referencia de gastos con `uso = kilometraje`
   (`tablas_de_referencia.uso`, validado contra `Dominio.usos_de_tabla`), su fila más específica para
   país/ciudad/fecha; sin tabla o fila, `EXPENSE_MILEAGE_RATE`.
5. **Tipos de documento.** `expense_attachments.document_type` ∈ `POLICY_DOCUMENT_TYPES` (por defecto
   `receipt,invoice,ticket,attendees,other`), editado con chips en Políticas → Tipos de documento
   (`servicio.guardar_tipos_de_documento`: claves cortas, no se quita uno en uso).
6. **Migración 166** (idempotente: la política conserva el id de la fila; downgrade la rehace por la
   marca `NOTA` en `nota_de_version`). Ver `_reglas` para la equivalencia exacta.
7. **Ejemplos**: `Dominio.ejemplos` + `servicio.cargar_ejemplos`: tablas (reutiliza las del mismo
   nombre) y políticas en BORRADOR; quita de los ejemplos los tipos de documento no configurados.
8. **Avisos y auto-aprobación necesitan solicitud.** En gastos, `notify` y `auto_approve` de una política
   solo actúan dentro de `create_approval_request`. Si `fuentes.abrir` no abre solicitud (sin flujo que
   encaje y sin niveles ni pasos de política), no se avisa a nadie y el gasto queda `submitted` para un
   responsable. Ausencias sí llama a `ejecutar_avisos` en ese caso (`solicitudes._abrir_flujo`).
9. **Revisar desde Gastos** (`POST /expenses/{id}/review`, `require_any_manager` + ABAC `approve`) pasa
   antes por el control presupuestario (`presupuestos_seguir.control_de_gasto`: aviso, o 409 con
   `BUDGET_CONTROL_POLICY` en bloquear), igual que la bandeja (`fuentes.comprobar_antes`).

Pantallas y uso para la persona y el administrador: README, «Expenses — `/expenses`». Configuración de
políticas y tablas: README, «Policies & rules engine — `/settings/policies`».

Tests: `tests/test_gastos_sobre_motor_de_politicas.py`.

## 22 quater. Ausencias gobernadas por reglas (tarea #25, revisión 167)

Reglas de arquitectura:

1. **Un solo motor de reglas.** Toda regla de ausencias es una política del dominio `ausencias`
   (`app/services/politicas/dominios/ausencias.py`): campos tipados (tipo, días, periodo, turno,
   equipo, departamento, oficina, rol, persona, sustituto, saldo que queda, antelación, días
   seguidos, compañeros ausentes, cobertura que queda…), resultado propio `cupo` y `waitlist`.
   El motor gana tres extensiones genéricas (documentadas en 22 bis y en el README):
   `Dominio.resultados_propios` + `resolver_propio` (resultados de un solo dominio, validados por
   sus `Parametro` y pintados genéricamente por `EditorDeResultados`), `admite_lista_de_espera`
   (decisión `block > waitlist > review > auto_approve > allow`), `tipos_de_documento` y
   `opciones_dinamicas` (opciones `enum` por empresa en `/policies/options`), y el tipo de campo
   `periodo` (`overlaps` / `not_overlaps`). Evaluar sigue sin efectos: `resolver_propio` solo lee.
2. **Un solo motor de aprobaciones.** La aprobación es SIEMPRE `approval_engine` con
   `entity_type = leave`: el flujo del tipo (`tipos_de_ausencia.workflow_id`, nuevo parámetro
   `fuentes.abrir(…, workflow_id=)`) o el que elijan sus condiciones, más niveles y pasos de las
   políticas. `POST /absences/{id}/review` con solicitud abierta es un VOTO en ella
   (`decide_approval_request`); sin solicitud, la decisión directa de un responsable. La decisión
   final llega siempre a `solicitudes.aplicar_decision` (vía `fuentes.aplicar` →
   `absence_service.review_absence`). `approved_by` queda como «quién cerró»; el historial es
   `approval_decisions` + `eventos_de_ausencia`.
3. **Cupos sin carreras** (`app/services/ausencias/cupos.py`): plazas en `huecos_de_cupo` (única
   por empresa, clave, fecha, turno, grupo), creadas con `INSERT … ON CONFLICT DO NOTHING` y
   bloqueadas con `SELECT … FOR UPDATE` por id (PostgreSQL); en SQLite, cerrojo de proceso +
   `UPDATE version` (cerrojo de escritura). La reserva va en una transacción NUEVA, después de
   confirmar la ausencia; se cuentan las reservas `ocupa` con las filas bloqueadas. Una petición
   es atómica (todas sus plazas o espera en todas). La `clave` del cupo la genera la pantalla y
   viaja con las versiones de la política. Promoción: la primera petición en espera (por
   `pedida_en`) que ya cabe entera.
   Siembra (`cupos._sembrar`, `cupos.sembrar_politica` vía el gancho `Dominio.al_publicar`): una
   plaza sin reservas y cada política publicada con cupos cuentan las ausencias que ya existían
   (aprobadas; y pendientes si la plaza se da al pedir) que encajan en esa regla, turno y grupo.
   Ampliar (`solicitudes.ampliar`): evalúa el tramo nuevo, reserva o espera sus plazas y vuelve a
   aprobación si hace falta; rechazarla devuelve el fin anterior (`_rechazar_ampliacion`).
4. **Momento de la plaza**: `solicitud` (reserva al pedir; en espera no se abre el flujo hasta
   tener plaza) o `aprobacion` (reserva al aprobar; sin plaza queda aprobada en espera y pasa a
   aprobada al liberarse una). `si_lleno` son resultados del motor: `waitlist`, `block` (409 al
   reservar, con la ausencia guardada como `rejected`; 422 sin guardar si la evaluación ya lo ve
   lleno) u otros (cupo blando: ocupa «por encima»). Dar plaza a mano (`POST /absences/{id}/promote`,
   no a uno mismo) también ocupa «por encima» si el cupo sigue lleno.
5. **Turnos y cuadrante** (`turnos.py`): rotaciones (`patrones_de_turnos`, ciclo de N días +
   miembros con desfase; una persona no puede estar en dos a la vez) y cambios por día
   (`asignaciones_de_turno`, mandan sobre rotación y festivo). Festivos de `holidays`
   (`applies_to` vacío = todos; si no, el país de la oficina del turno, o su nombre si no tiene
   país). Sin cuadrante, lunes a viernes salvo festivos.
   `cobertura()` da por día y turno requeridas/asignadas/ausentes/pendientes/en espera, y con
   `simular` el impacto de una ausencia (vista previa, campo `cobertura_restante`, bandeja).
6. **Documentos** (`documentos.py`): sobre el almacén de siempre (`s3_service.file_storage`,
   `core.uploads.validate_upload`, `collaboration._storage.scan_with_av`, URL firmada); una
   `Document` por versión, enlazada por `documentos_de_ausencia` (borrarla por retención borra el
   documento). No salen en `/documents` y `documents_service.check_document_access` consulta
   `documentos.acceso_por_el_repositorio`. Categoría especial: la persona, RRHH y
   `acceso_especial_ausencias` (un admin solo si está). Ver, descargar y denegado →
   `document_access_logs` + `audit_logs`. Retención y bloqueo legal: tipo `absence_documents`
   (`app/db/bloqueo_legal.py`, campos `id`, `absence_id`, `user_id`).
7. **Plazos**: requisitos por tipo (`requisitos_documentales_de_tipo`), por política
   (`require_attachment` con claves de `tipos_de_documento_de_ausencia`) y a mano.
   `app.worker.ausencias_pasada_diaria` (07:10, `_por_organizacion`): genera los que se repiten,
   recuerda una vez antes de vencer, marca vencidos y escala una vez a `escalar_a` (o al
   responsable; al que lo pidió si es manual); y reintenta la lista de espera.
8. **Compatibilidad**: `absences.type` guarda la clave del tipo (el enum era `absencetype`; la 167
   lo pasa a `VARCHAR(50)` y crea los 7 tipos de sistema en cada empresa; `catalogo.asegurar`
   los crea en una empresa nueva). `AbsenceType` queda como lista de claves de sistema. El API
   antiguo (`type`) sigue valiendo. Saldo de vacaciones: todos los tipos con `saldo = vacaciones`
   (`ausencias/saldos.py`; `absence_service.get_vacation_balance` lo usa).
9. **Visibilidad**: `privada` → el tipo y el motivo solo los ven la persona, RRHH y el acceso
   especial (`absence_service.puede_ver_tipo`); `equipo` → su equipo y quien gestiona.
10. **Sin JSON a mano**: tipos, documentos, turnos, rotaciones, cuadrante y cupos se editan en
    `AbsencesPage` → Configuración (`components/ausencias/admin/*`) y en Políticas.
11. **Permisos** (`endpoints/ausencias.py`, `absences.py`): tipos, tipos de documento y turnos →
    admin y hr; rotaciones y `PUT /roster` → `require_any_manager`; conceder o retirar acceso especial
    y cargar el ejemplo → admin. `POST /{id}/review` → `require_any_manager` y nunca sobre lo propio
    (`exigir_que_no_sea_suyo`). Pedir o dispensar documentos, ampliar y dar plaza →
    `documentos.exigir_gestion` (RRHH, admin o responsable hasta 3 niveles). Ver una ausencia
    (`consultas.visible`): la persona, su sustituto, sus responsables, quien la aprueba y los roles
    admin, hr, pm y team_lead; si no, 404.
12. **Límites reales**: los documentos no bloquean ni la petición ni la aprobación (solo recordatorio,
    vencido y escalado); un requisito `require_attachment` de política vence el mismo día de la
    petición; `require_justification` de política no se exige en ausencias. Un aprobador sin rol de
    responsable ve la solicitud en «Por decidir» pero `/review` le da 403: decide en `/approvals`.
    No se cancela una ausencia aprobada ya iniciada (400).

Uso y configuración para la persona y el administrador: README, «Absences — `/absences`».

Tests: `tests/test_ausencias_reglas.py` (cupo al pedir y al aprobar, promoción al cancelar y
rechazar, bloqueo si lleno, carrera por la última plaza con 8 hilos, documento con plazo,
recordatorio y escalado, parte médico: acceso y auditoría, retención, migración 167, API
antiguo, flujo multinivel, aislamiento por empresa, ejemplos).


## Turnos en el planificador y ausencias por horas (17-11-2026, revisión 180)

### Horario efectivo: una sola fuente
`app/services/horario/efectivo.py` calcula, para cada persona y día, `DiaEfectivo`:
tramos teóricos, pausa, origen (`cambio` > `rotacion` > `jornada` > `empresa`),
turno o jornada, festivo, fuera de contrato y ausencias con los tramos que quitan.
Horas teóricas = tramos − pausa; horas disponibles = lo que queda tras festivo
(salvo turno que trabaja festivos), contrato y ausencias (la pausa se descuenta en
proporción). Turno partido (`turnos.tramos`) y que cruza la medianoche (cuenta el
día en que empieza). Jornadas (`jornadas_laborales`) por día de la semana, asignadas
(`asignaciones_de_jornada`) a empresa, sede, departamento, equipo, grupo o persona,
con vigencia o cada año (verano); gana prioridad, luego concreción, luego la temporal.
Festivos por sede: `holidays.office_id`; `applies_to` sigue valiendo para país/ciudad.
`users.office_id` es la sede de la persona.

Lo usan: `planificador/calendario.py` (`Calendario.horas_por_fecha` y `horas(d)`;
horizonte `PLANNING_SCHEDULE_HORIZON_DAYS`, más allá el patrón con la jornada media),
`nivelacion.py` (capacidad diaria = horas de ese día; reparto proporcional),
`carga.py` (capacidad semanal = suma de horas), `resource_analytics.get_user_week_hours`
(`scheduled_hours`, `available_hours`; `capacidad_de_semana`), reservas
(`comprobar_capacidad` cuenta los días que trabaja), previsión (`_capacidad`),
`ausencias/turnos.dias_que_cuentan`, cobertura (`parciales`), saldos y bolsa.

### Ausencias por horas
`absences.modo` (dias|horas), `start_time`/`end_time` (franja de cada día) y
`scheduled_hours`. `reglas.medida` mide sobre el horario: días equivalentes,
horas, máximo por día y horas fuera de horario. `solicitudes.medidas_finales`
aplica `redondeo` y `saldo_negativo` de las políticas. `_solapada` deja dos
franjas distintas el mismo día. Cupos por franja: `franja_minutos` (la franja va en
el grupo, «grupo@HH:MM»; sin cambiar la tabla).

### Saldos, permisos y bolsa
`saldos.py`: periodo (`periodo_saldo`, `inicio_periodo_mes`), unidad (días u horas;
conversión con la jornada media de la persona), lotes (derecho —ficha de
vacaciones, tabla de referencia `derecho_tabla_id`, cupo, ajuste por defecto—,
arrastre `arrastre_max`/`arrastre_caduca_meses` hasta `ABSENCE_BALANCE_CARRY_PERIODS`
periodos atrás, movimientos con caducidad `caduca_meses`), consumo por orden de
caducidad (`repartir`, puro), prorrateo por alta. `movimientos.py`: ajustes de RRHH
(auditados). `bolsa.py`: exceso imputado − horario con factores, umbral y topes;
un movimiento idempotente por persona/tipo/día; pasada diaria `HOUR_BANK_RECALC_DAYS`;
`solo_horas_extra` (rev. 184): solo el exceso cubierto por horas extra aprobadas en bolsa.
Tipos: `modos`, `retribuido`, `saldo` = vacaciones|propio|bolsa.

### Motor de políticas
Campos nuevos del dominio `ausencias` (ver su cabecera), tipo de campo `hora`,
campos con varios valores (grupos, tipos que solapan: «es/está en» = alguno),
resultados propios `saldo_negativo` y `redondeo`, uso de tabla `derecho`, y en el
ámbito `grupos`, `excepto_personas`, `excepto_grupos` (las excepciones mandan).

### Pantallas
Formulario con modo días/horas y vista previa; administración: Jornadas, Festivos
(por sede), Personas (ficha laboral, saldos en días y horas, ajustes, recalcular
bolsa) y Horario (rejilla persona×día); turnos partidos y pausa; tipos con modos,
periodo, arrastre, caducidad, tabla y reglas de bolsa; calendario, cuadrante y
cobertura con ausencias parciales; planificador con modo «Horario»; políticas con
condiciones de hora, grupos y excepciones.

Migración `180_turnos_y_ausencias_por_horas`. Tests:
`tests/test_turnos_y_ausencias_por_horas.py`,
`frontend/src/__tests__/FormularioDeAusenciaHoras.test.tsx`.

## Horas extra y trabajo fuera de horario (18-11-2026, revisión 184)

Peticiones de horas extra aprobadas por flujos, sin motor paralelo: horario
efectivo (`app/services/horario/`), motor de políticas (dominio `horas_extra`),
motor de aprobaciones (tipo `overtime`) y bolsa de horas (`ausencias/bolsa.py`).
Código: `app/models/horas_extra.py`, `app/services/horas_extra/` (config, calculo,
reglas, solicitudes, control, consultas, ejemplos),
`app/services/politicas/dominios/horas_extra.py`, `app/api/v1/endpoints/horas_extra.py`
(`/api/v1/overtime`); pantalla `/overtime` (`frontend/src/pages/HorasExtraPage.tsx`,
`components/horas-extra/`, `services/api/horas-extra.ts`), en «Mi trabajo» tras Ausencias.

**Peticiones.** Previa (autorización antes: fecha, franja u horas, motivo, proyecto
y ticket opcionales, sustituto, tipo `laborable` | `fuera_de_franja` | `festivo` |
`no_laborable` | `guardia`) o posterior (exceso imputado sin autorizar). Registro
coherente: el tipo tiene que cuadrar con el día según su horario y la franja no
puede caer dentro de él. Compensación `pago` | `bolsa` | `ninguna` entre las que
permite la empresa; una regla puede fijarla (`set_field compensacion`) y fijar el
factor de pago (`set_field factor`). Un responsable puede pedir para su equipo.

**Configuración** (`config_horas_extra`, por empresa, auditada; sin fila = desactivado
y la imputación como antes): control al imputar `ninguno` | `avisar` | `regularizar` |
`bloquear`, tolerancia en minutos, compensaciones, flujo, tipo de bolsa, pedir en
nombre de otro, motivo obligatorio. Presupuestos de horas por empresa,
departamento, equipo o proyecto, al mes o al año (`presupuestos_de_horas_extra`).

**Límites sin código.** Campos del dominio: horas, horas fuera de horario, clase de
día, acumulados del día/semana/mes/año y del año solo pagadas, antelación, descanso
entre jornadas, días seguidos, presupuesto restante, quién pide, rol, equipo,
departamento, sede, grupos, contrato, proyecto, motivo, sustituto. «Cargar ejemplos»
(`POST /policies/examples/horas_extra`) crea BORRADORES con el máximo legal español
de 80 h/año pagadas (editable), 4 h/día, 10 h/semana, 12 h de descanso, 6 días
seguidos, antelación de 24 h, presupuesto agotado (+1 nivel), factores por tipo de
día, guardia pagada con sustituto y motivo a partir de 2 h.

**Aprobación.** `fuentes.abrir(…, "overtime")`: flujo de la configuración (niveles,
grupos, paralelos, escalado por timeout, aprobación por correo) más los niveles y
pasos de las políticas; sin flujo decide su responsable (cadena), RRHH o
administración. Quien aprueba puede autorizar menos horas de las pedidas.

**Control al imputar** (`horas_extra/control.py`, desde el alta, la edición y el
borrado de imputaciones): `bloquear` → 422 `horas_extra_sin_autorizar` si el día
queda con exceso no cubierto por lo aprobado (el tope semanal se amplía con lo
aprobado); `regularizar` → una declaración posterior pendiente por persona y día
(se recalcula y se anula sola); `avisar` → aviso a la persona y su responsable y
`audit_log OVERTIME_UNAUTHORIZED`. `POST /overtime/regularize` lo pasa por un periodo.

**Bolsa.** Regla nueva del tipo de bolsa `solo_horas_extra`: solo genera bolsa el
exceso cubierto por horas extra aprobadas con compensación en bolsa. El pago se
liquida con referencia de nómina (`/overtime/{id}/settle`, `/overtime/payroll`).

**Ciclo visible.** `GET /overtime/{id}`: línea de tiempo (`eventos_de_horas_extra`),
evaluaciones de reglas con su explicación, pasos y decisiones con quién/cuándo/nota,
escalados, día (horario, imputado, exceso real frente a lo autorizado),
imputaciones, compensación y liquidación. Resumen por persona/equipo/departamento/
proyecto frente a los umbrales de las reglas publicadas y a los presupuestos, y
lista de horas fuera de horario sin autorizar.

**GRC.** Auditoría de cada cambio de estado, configuración y presupuesto (las reglas,
en Políticas); segregación (nadie decide lo suyo ni lo que pidió para otro, también
en la bandeja: `fuentes.comprobar_antes`; módulo SoD `timesheets`); retención y
bloqueo legal `overtime_requests` (solo cerradas); RGPD acceso/portabilidad con
sus horas extra (y se conservan en la supresión: registro de jornada); informe de
cumplimiento `overtime_limits` y `overtime_unauthorized`; visibilidad mínima
(persona, su cadena de responsables, PM de sus proyectos, quien aprueba, RRHH y
administración). `overtime` cuenta como entidad financiera en el registro de
aprobaciones (escalados incluidos).

Migración `184_horas_extra` (idempotente). Tests: `tests/test_horas_extra.py`,
`frontend/src/components/horas-extra/__tests__/logica.test.ts`.

## Licencias y hardware — fases 1 y 3 (16-11-2026)

Base sólida (fase 1) y costes y trazabilidad (fase 3) del módulo ALM. Migración
`170_alm_titulares_ciclo_y_costes`. Código: `app/models/alm.py`, `app/services/alm_asignaciones.py`,
`alm_ciclo_de_vida.py`, `alm_actas.py`, `alm_costes.py`, `alm_renovaciones.py`, `alm_conciliacion.py`,
`alm_ajustes.py`, `alm_service.py`; endpoints en `app/api/v1/endpoints/alm.py`; pantalla `/alm`
(`frontend/src/pages/ALMPage.tsx`, `pages/alm/*Tab.tsx`, `components/alm/` y `services/api/alm.ts`).

**Asignación universal** (`ALMAsignacion`). La tabla `alm_license_assignments` se amplía en el sitio
(mismos ids) y pasa a guardar licencias **y** activos: titular persona, proyecto, departamento,
cliente o equipo; modo asignación, préstamo o bolsa; desde/hasta (previsto) y fin real; motivo,
quién asignó, aprobación, cierre con su motivo e imputación del coste. Nunca se borra: se cierra.
Cada paso queda en `alm_eventos`, inmutable (un `before_update`/`before_delete` lo impide):
«quién tuvo qué, cuándo y por qué» por recurso (`GET /alm/history?license_id|asset_id`) o por
titular (`?holder_type&holder_id`). Columnas renombradas: `user_id → holder_user_id`,
`project_id → holder_project_id`, `asset_id → holder_asset_id` (el equipo de una licencia por
dispositivo), `expires_at → valid_to`; `asset_id` es ahora el activo asignado.
- Aprobación: si la empresa tiene un flujo activo para el tipo `alm_assignment` (bandeja de
  aprobaciones), la asignación nace `pending` (reserva su asiento) y la decisión final la activa o
  la rechaza (`approval_engine.fuentes`). Sin flujo, queda activa.
- `ALMAsset.assigned_to_id`, `project_id` y `department_id` se mantienen como reflejo del titular
  vigente (los leen la CMDB y los informes); el estado y el titular de un activo ya no se cambian
  editándolo (`409 alm_estado_por_accion`): van por las acciones.

**Modelos de licencia** (`ALMLicense.metric`): `named_user` (persona; un proyecto, departamento o
cliente recibe una **bolsa** de asientos y la reparte con asignaciones hijas), `device`,
`concurrent` (las asignaciones no consumen; cumplimiento por pico medido: `alm_picos_concurrencia`,
`registrar_pico`, ventana `ALM_CONCURRENT_PEAK_WINDOW_DAYS`), `volume` (cada asignación consume su
cantidad) y `site` (sin límite). Niveles: `tier`, `tier_rank` (mayor = superior), `sku`. La
migración deduce la métrica del tipo antiguo.

**Hardware.** Comprado (`ordered`) → almacén (`available`) → asignado (`in_use`) o prestado
(`on_loan`, con fecha de devolución) → reparación → baja (`retired`, con motivo) → reciclaje
(`disposed`, con destino e importe); perdido/robado/recuperado. `POST /alm/assets/{id}/assign`
(asignar o prestar), `POST /alm/assignments/{id}/return` (devolver, con checklist, estado y
«a reparación») y `POST /alm/assets/{id}/lifecycle` (el resto; transiciones en
`alm_ciclo_de_vida.TRANSICIONES`). **Actas** (`alm_actas`): al entregar o devolver a una persona,
checklist (`ALM_HANDOVER_CHECKLIST`), estado físico y observaciones; PDF en el sistema de
documentos y solicitud de firma en el módulo de firma electrónica con `ALM_ACT_ESIGN_PROVIDER`
(`manual`: la persona firma en la aplicación —`POST /alm/acts/{id}/sign`, solo ella—, con IP y
huella en el historial; `docusign`/`adobe_sign`: el proveedor y su webhook). Fotos del estado y
documentos: `alm_adjuntos` (`/alm/assets/{id}/attachments`, `/alm/acts/{id}/attachments`).

**Arreglos.** La clave de licencia se guarda cifrada (`app.core.encryption`; la migración cifra
las que había) y solo sale por `GET /alm/licenses/{id}/key` (gestores; queda en historial y
auditoría); el listado enseña `license_key_hint` (4 últimos). El panel ya no suma licencias
canceladas o borradas ni cuenta dos veces licencia y contrato (`coste_anual_vigente`). Las métricas
de `services/metrics/alm.py` filtran lo borrado, cuentan asientos por cantidad y usan `mobile`.
`alm_renewal_alerts` pasa a ser el registro de avisos enviados. Permisos más estrictos: lo
económico y de terceros, solo gestores; los catálogos que usan los selectores, personal interno
(sin subcontratistas).

**Coste por titular y día** (`alm_costes`, fase 3). Cuota anual / 365 entre inicio y vencimiento;
un contrato con `annual_value` se reparte entre sus licencias sin cuota (lo que sobra es una línea
del contrato, nunca dos veces); perpetua amortizada en `amortization_months`
(`ALM_PERPETUAL_AMORTIZATION_MONTHS`); equipo amortizado (precio − residual en sus años) o renting
(`lease_monthly_cost`). Con total de asientos cada asiento cuesta lo suyo y lo no asignado es
**ocioso**; la bolsa reparte su coste entre sus hijas. Imputación: lo explícito de la asignación
(`charge_*`), si no el titular o la bolsa; centro del recurso o del departamento del titular;
cliente del titular o del proyecto. `GET /alm/costs?from&to&group_by` y
`/alm/costs/rebillable` (margen `ALM_REBILL_MARKUP_PCT`; refacturable: el de la asignación o el
del recurso).
- Rentabilidad: `costes_de_proyecto.costes_externos` devuelve `alm`, que suma en el coste total
  (`profitability_service`: `alm_cost`) y en el AC de EVM (`evm_service`).
- Presupuestos: el comprometido de ALM sale de este reparto (solo cuotas, sin amortizaciones) y
  no cuenta un mes ya cubierto por una factura de proveedor pagada con un gasto.

**Renovaciones** (`alm_renovaciones`, barrido diario `app.worker.alm_daily` 07:10). Fecha: la de
renovación del contrato (o su fin), o el vencimiento de una licencia sin contrato
(`ALM_LICENSE_NOTICE_DAYS`). Avisos al responsable o a `ALM_RENEWAL_NOTIFY_ROLES`:
`ALM_RENEWAL_LEAD_DAYS` antes del fin del preaviso, el último día de preaviso, al prorrogarse sola
y al vencer. Decisión (`POST /alm/renewals`): renovar, reducir (asientos o coste nuevos) o cancelar
(motivo obligatorio), con foto del uso que había (`uso_de_licencia`, que lee la fase 2 si está).
Se aplica al llegar la fecha; sin decisión, `auto_renew` prorroga un periodo y, si no, vence.
Préstamos: aviso a la persona `ALM_LOAN_REMINDER_DAYS` antes y semanal mientras siga vencido.

**Conciliación** (`alm_conciliacion`). Factura de proveedor (`alm_facturas_proveedor`) frente a lo
que el contrato dice que cuesta su periodo (meses enteros: anual/12 × meses; si no, por días) y
frente al gasto que la paga (categoría de `ALM_EXPENSE_CATEGORIES`, aprobado o reembolsado), con
tolerancia `ALM_RECONCILIATION_TOLERANCE_PCT`; los motivos salen como códigos (`alm.rec_*`). Una
discrepancia revisada se acepta con nota. `GET /alm/invoices/missing`: periodos de contratos
activos sin factura. Un gasto enlazado a una factura ya no cuenta en «gastos» del proyecto.

**Interfaz para otras fases.** Fase 2 lee `ALMAsignacion` (`titulares_vigentes`,
`asignaciones_de_usuario`), escribe con `registrar_pico` y `liberar(tipo="released",
origen="usage")` e implementa `app.services.alm_uso.uso_de_licencia(db, license_id)` con las claves
documentadas en `alm_renovaciones`. Fase 4 usa `asignar`, `prestar`, `liberar(commit=False)`,
`devolver`, `liberar_licencias_de_usuario`, `equipos_de_usuario`, `asignacion_vigente_de_activo`,
`alm_actas.firmar` y `alm_costes.lineas`.

**Ajustes** (grupo `alm`, «Licencias y hardware»): `ALM_HANDOVER_ACT_ENABLED`, `ALM_HANDOVER_CHECKLIST`,
`ALM_ACT_ESIGN_PROVIDER`, `ALM_LOAN_DEFAULT_DAYS`, `ALM_LOAN_REMINDER_DAYS`, `ALM_RENEWAL_LEAD_DAYS`,
`ALM_LICENSE_NOTICE_DAYS`, `ALM_RENEWAL_NOTIFY_ROLES`, `ALM_PERPETUAL_AMORTIZATION_MONTHS`,
`ALM_REBILL_MARKUP_PCT`, `ALM_RECONCILIATION_TOLERANCE_PCT`, `ALM_RECONCILIATION_EXPENSE_WINDOW_DAYS`,
`ALM_EXPENSE_CATEGORIES`, `ALM_CONCURRENT_PEAK_WINDOW_DAYS`.

**Límites conocidos.** La refacturación es un informe (importe por cliente con margen): no genera
facturas al cliente. El PDF del acta sale en el idioma de la plataforma (es o en; el chino cae a
inglés). Los avisos se guardan como texto en el idioma de la plataforma (la bandeja no traduce).
En PostgreSQL el downgrade no puede quitar los estados nuevos del tipo `alm_assetstatus`.

Pruebas (escritas, no ejecutadas): `tests/test_alm_fases_1_y_3_2026_11.py` y
`frontend/src/__tests__/AlmFases13.test.tsx`.

## Licencias y hardware — fase 2: uso real (16-11-2026)

Quién usa (o dejó de usar) cada licencia y cada equipo, según fuentes externas e
internas, y qué se hace con ello. Código: `app/services/alm_uso/`, modelo
`app/models/alm_uso.py`, API `/api/v1/alm/uso/*` (`app/api/v1/endpoints/alm_uso.py`),
pantalla Licencias → **Uso real** (`frontend/src/pages/alm/uso/*`), migración
`171_alm_uso_real`. Se apoya en la asignación universal de las fases 1 y 3
(`ALMAsignacion`: `holder_user_id` persona, `holder_asset_id` equipo; `ALMLicense.metric`,
`sku`, `tier_rank`).

**Evidencias de uso** (`alm_uso_evidencias`): una fila por (empresa, fuente, titular, producto)
con titular persona (UPN/correo → `users`) o dispositivo (nº de serie o nombre → `alm_assets`),
producto/SKU, licencia de ALM (`license_id`) y asignación (`assignment_id`), último uso,
frecuencia (días con uso en el periodo), servicios usados (`{servicio: fecha}`), si la fuente
dice que lo tiene asignado, fiabilidad de la fuente (`alta`/`media`/`baja`, por proveedor o
fijada por la empresa en la conexión) y fecha de lectura. Cada lectura completa pone al día las
filas y marca como no vistas las que la fuente ya no da (p. ej. le quitaron la licencia); una
lectura cortada por el tope de páginas no retira nada.

**Estado derivado** (`estado.py`), por asignación y por licencia: `en_uso` / `infrautilizada` /
`sin_uso` / `sin_datos`. Umbrales por empresa (grupo de ajustes `licencias_uso`):
`ALM_USAGE_IDLE_DAYS` (60), `ALM_USAGE_UNDERUSED_DAYS` (30), `ALM_USAGE_MIN_ACTIVE_DAYS` (4, solo si
la fuente da frecuencia), `ALM_USAGE_STALE_DATA_DAYS` (7). Los días de ausencias APROBADAS se
descuentan (`dias_sin_uso_efectivos`). Cuenta desactivada en la fuente → `sin_uso`. Instalado
sin dato de uso → `sin_datos` (instalado no es usado). Asignación reciente nunca usada →
`sin_datos` hasta el umbral de infrautilizada. Con varias fuentes manda el uso más reciente.

**Lectura para otros módulos** (`app/services/alm_uso/__init__.py`, docstring completo):
`uso_de_licencia(db, license_id)` → `asignados, total, en_uso, infrautilizadas, sin_uso, sin_datos,
pico_concurrente, fuente, medido_en` (contrato con `alm_renovaciones.uso_de_licencia`) más
`estado`, `uso_sin_asignacion`, `ultimo_uso`, `asignaciones`; `uso_de_asignacion(db, id)`;
`uso_de_licencias(db, org, ids)`. `sin_datos` no es `sin_uso`.

### Fuentes (conectores) y permisos de API

Interfaz común `proveedores/base.py::ProveedorDeUso` (registro en `proveedores/__init__.py`):
`leer(ctx) → ResultadoDeLectura(evidencias, dispositivos, derechos, aplicaciones, avisos)`,
`probar(ctx)`. El proveedor no escribe: `conciliacion.py` concilia y guarda para todos. Toda
llamada sale por `proveedores/http.py` (espera `OUTBOUND_HTTP_TIMEOUT_SECONDS`, 30 s por
defecto en este módulo; URLs y redirecciones validadas contra SSRF con
`outbound_url.cliente_httpx`, https obligatorio; errores con código estable sin secretos).
Credenciales: proveedores `alm_m365`, `alm_google`, `alm_okta`, `alm_jamf` del registro de
`integration_credentials` (cifradas, auditadas, nunca devueltas). Se leen SOLO con la fila de la
empresa (`conexiones.credenciales`): ni la global ni el entorno, para que una empresa no lea
con las credenciales de otra.

| Fuente | Estado | Qué lee | Permisos |
|---|---|---|---|
| Microsoft 365 / Entra ID (`m365`) | Implementado; verificado con dobles | `subscribedSkus` (comprados/consumidos), `users` con `assignedLicenses` y `signInActivity`, informes `getOffice365ActiveUserDetail` y `getM365AppUserDetail` (CSV). El último uso de un SKU es el de los servicios que ESE SKU incluye (planes de servicio); si no incluye ninguno medido, el inicio de sesión con fiabilidad rebajada. Sin `signInActivity` o sin informes: aviso y sigue. Nombres ocultos en informes: aviso. | Aplicación de Entra ID con permisos **de aplicación** y consentimiento de administrador: `Organization.Read.All`, `User.Read.All`, `AuditLog.Read.All` (signInActivity; requiere Entra ID P1/P2), `Reports.Read.All`. Desactivar «ocultar nombres en los informes» (Centro de administración → Configuración → Informes). |
| Intune (`intune`) | Implementado; verificado con dobles | `deviceManagement/managedDevices` (nº de serie, último check-in, usuario principal, sistema, modelo) y `detectedApps` con sus dispositivos (hasta `ALM_USAGE_INTUNE_MAX_APPS`, las más extendidas; si hay más, no se retira ninguna instalación). | `DeviceManagementManagedDevices.Read.All` (aplicación), mismas credenciales `alm_m365`. |
| Google Workspace (`google`) | Implementado; verificado con dobles | Directory `users` (último acceso, suspendida), Licensing por producto (opción `productos`, por defecto `Google-Apps`; con `my_customer` necesita la opción `dominio`), Reports `usage/users` del día `hoy - retraso_informes_dias` (3) y Reports `activity/token` (aplicaciones autorizadas → software no controlado). | Cuenta de servicio con **delegación de todo el dominio** y los alcances `admin.directory.user.readonly`, `admin.reports.usage.readonly`, `admin.reports.audit.readonly`, `apps.licensing`; el administrador suplantado (`admin_email`) con privilegios de lectura de usuarios, informes y licencias. |
| Okta (`okta`) | Implementado; verificado con dobles | `users` (lastLogin, estado) → producto `okta`; `apps` activas y `apps/{id}/users` (asignación); System Log `user.authentication.sso` del periodo → último acceso y días con acceso por persona y aplicación. Paginación por cabecera `Link`. | Token de API de un administrador de solo lectura (`okta.users.read`, `okta.apps.read`, `okta.logs.read`). |
| Jamf Pro (`jamf`) | Implementado; verificado con dobles | `api/v1/computers-inventory` (GENERAL, HARDWARE, OPERATING_SYSTEM, USER_AND_LOCATION, APPLICATIONS). Solo ordenadores (no móviles). | Cliente de API (`/api/oauth/token`) con un rol que tenga «Read Computers». |
| Accesos a contecflow (`contecflow`) | Implementado | `users.last_login` y `user_sessions.last_seen_at` (días con sesión en el periodo) → producto `contecflow`. | Ninguno (interno). |
| SSO de contecflow (`contecflow_sso`) | Implementado | Sesiones `auth_method = sso` → producto `sso:<proveedor>` (azure_ad, okta, google…) y el proveedor de identidad como aplicación vista. | Ninguno (interno). |
| Agente de inventario (`agente_cmdb`) | Implementado | Lo ENVÍA el agente en `POST /sd/cmdb/agents/checkin`: nuevos campos opcionales `serial_number`, `manufacturer`, `model`, `primary_user`, `software: [{name, version, publisher, last_used_at}]`, `software_complete`. Alimenta `alm_assets` (por nº de serie o nombre; se crea si `ALM_USAGE_CREATE_ASSETS`) y `alm_software_installs`. La conexión se crea activa al primer envío; desactivarla lo ignora. No deja una fila de sincronización por check-in. | Token del agente (CMDB → Agentes). |

Añadir una fuente: subclase de `ProveedorDeUso`, su proveedor `alm_*` en
`PROVIDER_REGISTRY` si tiene credenciales, y `registrar(...)` en `proveedores/__init__.py`. La
conciliación, el registro, la pantalla de conexiones y el worker la recogen solos.

**Conciliación** (`conciliacion.py`): producto → licencia por mapeo explícito
(`alm_uso_mapeos`, pantalla Fuentes → Productos), si no por `ALMLicense.sku`, si no por un único
nombre normalizado; si hay varias candidatas no se adivina (sugerencia por parecido). Equipos:
rellena solo lo vacío del activo (y la IP / el sistema, que cambian), con historial
`inventario:<fuente>`. Una app desaparecida de una lista completa desactiva la instalación que
creó la propia conciliación (las manuales no se tocan).

**Sincronización** (`sincronizacion.py`): manual (`POST /alm/uso/conexiones/{id}/sincronizar`,
se encola con `segundo_plano.encolar`) y programada (`app.worker.alm_uso_sincronizar`, cada hora
al minuto 35; lee cada conexión activa cuando vence `ALM_USAGE_SYNC_INTERVAL_HOURS`). Cada
lectura deja `alm_uso_sincronizaciones` (leídos, nuevas, actualizadas, sin persona, sin
licencia, dispositivos, avisos, errores); una conexión que falla no para a las demás. Retención
`ALM_USAGE_SYNC_LOG_RETENTION_DAYS`. Tras leer se anota el pico de cada licencia `concurrent`
(personas distintas con uso en las últimas 24 h) con `alm_asignaciones.registrar_pico`: es un
pico diario, no de sesiones simultáneas, porque ninguna fuente integrada da sesiones abiertas.

### Recuperación (harvesting) con el motor de políticas

Dominio `licencias` (`app/services/politicas/dominios/licencias.py`), entidad = asignación de
licencia vigente de persona o equipo. Campos: días sin uso (y descontando ausencias), estado de
uso, frecuencia, fiabilidad, fuente, cuenta desactivada, datos desactualizados, licencia,
producto, proveedor, métrica, tipo, coste anual del puesto, días desde la asignación, ausente
hoy, titular, persona, rol, departamento, equipo, proyecto. Resultado propio `recuperar`
(días hasta avisar al responsable, a quién: responsable directo / jefe del proyecto /
responsable del contrato / nadie, días hasta liberar, aprobación sí/no, canales, mensaje).
Ejemplo cargable («Cargar ejemplos», se crea como borrador).

`recuperacion.pasada` (worker `app.worker.alm_uso_pasada_diaria`, 07:40): `aviso_persona` →
`aviso_responsable` → liberar (`alm_asignaciones.liberar(tipo="released", origen="usage")`) o
`pendiente_aprobacion` (bandeja de aprobaciones, tipo `license_reclaim`, si la empresa tiene flujo;
siempre también desde la pantalla). Protecciones que mandan sobre cualquier política: ausente
hoy (y el reloj del paso se para mientras), asignación más joven que `ALM_RECLAIM_GRACE_DAYS`,
sin datos o datos desactualizados, y «la sigo necesitando» (`ALM_RECLAIM_KEEP_DAYS`). Si la
persona vuelve a usarla, el proceso se cierra solo. Simulador:
`GET /alm/uso/recuperaciones/simulacion` (sin efectos; además el simulador genérico de
políticas funciona con este dominio).

### Ajuste de nivel, cumplimiento y software no controlado

- **Ajuste de nivel** (`ajuste.py`): reglas superior → inferior con los servicios que justifican la
  superior; se propone bajar a quien no usó ninguno en `ALM_RIGHTSIZING_WINDOW_DAYS`, con ahorro =
  coste unitario anual superior − inferior. Sugerencias de reglas por `tier_rank` del mismo
  producto. Aceptar asigna la inferior y cierra la superior (`tipo="transferred"`). Límite: E5→E3
  depende de servicios que los informes de Microsoft no miden; la regla solo puede usar lo que da
  la fuente (E3→E1 sí: aplicaciones de escritorio).
- **Cumplimiento** (`cumplimiento.py`): posición por licencia según `metric`: `named_user` = lo
  mayor entre asientos asignados y personas que la tienen o usan según la fuente; `device`/`volume`
  = equipos con el software; `concurrent` = pico; `site` = informativo. Estados `deficit`,
  `excedente`, `conforme`, `sin_limite`, exposición y coste ocioso, incidencias (caducada en uso,
  discrepancia con lo comprado según el fabricante, concurrente sin pico).
  `GET /alm/uso/cumplimiento/exportar?formato=csv|xlsx[&producto=]` para la auditoría (auditado).
  El informe anterior `GET /alm/compliance` (fase 1) sigue igual.
- **Software no controlado** (`no_controlado.py`): gastos `software` de
  `ALM_UNMANAGED_LOOKBACK_DAYS` no rechazados que no nombran ninguna licencia ni proveedor de ALM
  (agrupados quitando palabras de trámite; importe en la moneda de la empresa al tipo de cambio de
  su fecha), productos de las fuentes sin licencia, aplicaciones SSO/OAuth y software de equipos.
  Se proponen con `ALM_UNMANAGED_MIN_OCCURRENCES`. Alta → crea la licencia y mapea sus productos;
  descartar → los marca «no se controla».

### Permisos, auditoría y pruebas

Fuentes, credenciales, mapeos y registro: `require_admin`. Uso, recuperación, ajuste,
cumplimiento y no controlado: roles de gestión (datos de actividad de personas). Cada persona ve
sus licencias en recuperación (`/recuperaciones/mias`) y puede conservarlas. Toda consulta filtra
`organization_id` explícitamente (además del filtro de tenant y RLS). Auditoría en cada cambio de
conexión, mapeo, regla, decisión, liberación, alta/descarte y exportación.

Pruebas: `tests/test_alm_uso_fase2.py` (dobles de Graph/Intune, Google, Okta, Jamf; conciliación,
estado, recuperación, ajuste, cumplimiento, gastos, agente, permisos) y
`frontend/src/__tests__/AlmUsoReal.test.tsx`. Ningún conector se ha probado contra un tenant
real: solo con dobles.

## Licencias y hardware — fase 4: integración (16-11-2026)

Une ALM con personas, proyectos y el service desk. Código en `app/services/alm_integracion/`
(`bajas`, `kits`, `autoservicio`, `catalogo`, `proyecto`, `personas`, `_suministro`, `_comun`),
endpoints en `app/api/v1/endpoints/alm_integracion.py` (prefijo `/api/v1/alm/integracion`),
modelos en `app/models/alm_integracion.py`, migración `172_alm_altas_bajas_y_autoservicio`.
**No asigna, presta, libera ni devuelve por su cuenta**: todo pasa por `app.services.alm_asignaciones`
(`asignar`, `liberar`, `devolver`, `equipos_de_usuario`, `asignaciones_de_usuario`,
`asignacion_vigente_de_activo`), las actas por `app.services.alm_actas` (`firmar`, `acta_para`,
`serializar`) y el coste por `app.services.alm_costes.lineas` (fases 1 y 3).

**Bajas.** Cualquier camino que desactiva a una persona abre su expediente (`alm_bajas`):
`DELETE /users/{id}` y `PATCH` a `status=inactive` (motivo `manual`), SCIM `DELETE`, bulk y
`PUT/PATCH active=false` (`scim`), el fin de contrato de un subcontratado (`available_until`
pasado, `fin_contrato`) y las bajas programadas (`POST /alm/integracion/bajas/programar`).
- Licencias: `ALM_OFFBOARDING_LICENSE_RELEASE_DAYS` = 0 las libera en la misma transacción;
  N las libera N días después de la fecha de baja (barrido diario `alm_altas_y_bajas`, 06:50).
- Equipos: una devolución por equipo (`alm_devoluciones`) con su ticket en la cola
  `ALM_RETURN_GROUP_ID` (vacío: reglas de enrutado), enlazado al activo y con fecha límite
  `ALM_RETURN_DUE_DAYS`. Se sigue hasta el acta: `pendiente` → `recibida` (se registra la
  recepción: `alm_asignaciones.devolver` emite el acta de devolución) → `cerrada` (acta firmada,
  o sin acta que firmar; resuelve el ticket). `perdida` cierra la asignación como perdida. Si el
  equipo se devuelve desde la pantalla de ALM, la devolución se pone al día sola.
- Equipo sin devolver (`ALM_OFFBOARDING_PENDING_ASSETS`): `avisar` (avisa al manager o a
  `ALM_KIT_FALLBACK_ROLES`), `confirmar` (la baja manual exige `?confirmar_equipos=true`; queda
  anotado) o `bloquear` (la baja manual responde 409 `almint_baja_bloqueada`). SCIM y el fin de
  contrato **nunca** se bloquean (manda el proveedor de identidad o el contrato) y un fallo de ALM
  no corta su desactivación (punto de guardado). La baja se cierra sola cuando no queda nada.
- La pantalla de usuarios (Ajustes) enseña antes qué se libera y qué tiene que volver
  (`GET /alm/integracion/personas/{id}/previa-baja`).

**Kit de alta.** `alm_kits` + `alm_kit_elementos` por empresa: a quién aplica (todos, rol, puesto,
departamento o equipo) y qué licencias y tipos de equipo. Al crear a una persona (manual o SCIM,
si `ALM_KIT_ON_HIRE`) se propone la unión de los kits que le aplican; la confirma con un clic su
manager (o los roles de `ALM_KIT_FALLBACK_ROLES`). Al confirmar: licencia de la bolsa o con asiento
libre, equipo del almacén (el de mejor estado); lo que no hay se pide por compra (ticket en
`ALM_PURCHASE_GROUP_ID`). Cada elemento guarda su resultado.

**Mis equipos y licencias (`/my-equipment`, menú «Mi trabajo»).** Para toda persona con sesión,
también RRHH y subcontratados; todo acotado a quien pregunta (lo ajeno es 404). Lo asignado con
fechas de préstamo y devolución, pedir licencia o equipo (va al catálogo), devolver un equipo,
dejar una licencia, comunicar una avería (incidente en `ALM_BREAKDOWN_GROUP_ID` enlazado al
activo y a su CI) y ver y firmar las actas pendientes.

**Ficha de proyecto: pestaña «Recursos técnicos».** Bolsas de asientos del proyecto con su
reparto, lo asignado o cargado al proyecto, lo que tiene su equipo y el coste del periodo
(imputado, del equipo imputado fuera, ocioso y refacturable; `alm_costes`). Ven quienes ven el
proyecto (empleado y subcontratado: del equipo, solo lo suyo); el coste, el PM, administración y
quien ve presupuestos; asignar y liberar, el PM del proyecto y administración.

**Service desk.** Un ítem del catálogo es de ALM si tiene fila en `alm_items_de_catalogo`
(licencia o equipo, opcionalmente concretos). «Pedir licencia» y «Pedir equipo» se crean desde
Altas y bajas → Catálogo con la aprobación de varios niveles del motor común (modo `engine` del
catálogo, tipo `catalog_request`). Los datos de la petición viajan en los campos dinámicos `alm_*`
del ticket, así que vale igual desde el portal. Cuando el catálogo la da por buena
(`fulfillment_service.crear_tareas`), alta automática en ALM o compra (`alm_peticiones` guarda
qué se dio; «Reintentar el alta» tras recibir la compra). Los pasos `assign_license` /
`revoke_license` del aprovisionamiento actualizan ALM y, si traen `url`, también llaman al sistema
externo. Ticket ↔ recurso en los dos sentidos: `Ticket.linked_resource_type/_id`,
`GET /alm/integracion/tickets/{id}/recurso` (se ve en la ficha del ticket) y
`GET /alm/integracion/recursos/{asset|license}/{id}/tickets` (componente `TicketsDelRecurso`).

**Ajustes** (grupo `licencias_integracion`, en caliente por empresa): `ALM_OFFBOARDING_LICENSE_RELEASE_DAYS`,
`ALM_OFFBOARDING_PENDING_ASSETS`, `ALM_RETURN_DUE_DAYS`, `ALM_RETURN_GROUP_ID`, `ALM_PURCHASE_GROUP_ID`,
`ALM_BREAKDOWN_GROUP_ID`, `ALM_KIT_ON_HIRE`, `ALM_KIT_FALLBACK_ROLES`, `ALM_CONTRACT_END_OFFBOARDING`.

**Permisos.** Bajas, kits y programar: admin, RRHH y PM (kits: admin y RRHH); devoluciones,
propuestas y peticiones: roles de gestión (cada responsable decide las suyas); marcar ítems del
catálogo: admin. Todo cambio queda en auditoría (`alm_baja`, `alm_devolucion`, `alm_kit`,
`alm_kit_propuesta`, `alm_item_de_catalogo`, `alm_peticion`) y el historial inmutable de ALM.

Tests: `tests/test_alm_integracion_fase4.py`, `frontend/src/__tests__/AlmIntegracion.test.tsx`.

## Service desk — mejoras de mercado (16-11-2026)

Revisión de base de datos **174** (`alembic/versions/174_service_desk_mercado.py`, sobre la 173). Detalle de uso en `docs/SERVICE_DESK.md` (misma sección) y despliegue en `docs/DESPLIEGUE.md` (B.1).

- **IA en pantalla**: bloque *IA del ticket* (predicción de SLA, triaje con aplicar, duplicados con fusión —`GET /sd/tickets/{id}/duplicate-candidates`, `app/services/service_desk/duplicados.py`—, análisis y explicación, asignación inteligente), *Cola por riesgo* y panel del **agente autónomo** con modo `suggest`/`execute`, playbooks de serie apagables por empresa y registro paso a paso con aplicar/descartar (`/sd/autonomous/config`, `/executions/{id}/apply|discard`). Arreglado: playbooks, registro, estadísticas y pasada eran de toda la instalación; el triaje no se acotaba a la empresa.
- **Problemas y cambios**: `GestionDelProblema` (incidentes, RCA con plantillas del servidor y aprobación, cambio desde problema, KEDB con revisión y efectividad), `PlantillasRca`, `AnalisisDelCambio` (impacto con radio de la CMDB, matriz, vuelta atrás, pruebas, comunicaciones, ¿y si…?, reunión del CAB, aprobación directa y vía rápida) y `PanelDelCab`. Arreglado: `/sd/changes/{id}/impact-analysis|risk-matrix|*-plan|whatif` no comprobaban la empresa.
- **Catálogo**: aprobación en el motor común con el tipo `catalog_request` (`approval_engine/fuentes.py`), dominio de políticas `catalogo` (`politicas/dominios/catalogo.py`), tareas estructuradas por etapas (`sd_service_item_tasks`, `fulfillment_service.py`) y catálogo inteligente en el formulario.
- **SLA y estados**: `sd_sla_rules` (`reglas_sla.py`, se aplica al abrir y al recalcular), `sd_ola_targets` (OLA por prioridad en `sla_monitor_service`), festivos solo en calendarios SLA (`sla_calendars.applies_to_all`, `sla_calendar_holidays.sla_policy_id`; `sd_sla_holidays` y `/sd/sla-holidays` desaparecen) y ciclos de vida por tipo (`ciclos_de_vida.py`, `sd_tickets.lifecycle_state`; `status` sigue siendo el estado base).
- **Puesto del agente**: aviso de colisión por `ws/notifications` (`ticket_presence`, `presencia.py`), contexto del cliente con equipos y licencias de ALM (`GET /sd/tickets/{id}/customer-context`) y panel personal (`/sd/dashboard/layout`, ahora por persona; el de empresa, de admin).
- **Canales**: Slack interactivo (comandos del service desk en la tabla común de Slack/Teams, botones en `/sd/channels/slack/interactions`, `canal_slack.py`), WhatsApp Cloud API (`canal_whatsapp.py`, credencial `whatsapp`), chat en vivo del portal con traspaso a agente y bandeja de conversaciones (`conversaciones.py`, `/sd/channels/*`).
- **CMDB**: pantallas de descubrimiento, reconciliación, deriva, impacto y clases propias (`sd_ci_classes`, `sd_configuration_items.ci_class`, `/sd/cmdb/ci-classes`). Arreglado: la configuración de los proveedores (credenciales) se guardaba en claro; ahora cifrada.
- **Asistente del portal que actúa** (`/sd/portal-assistant/*`, `asistente_del_portal.py`): estado de tickets, petición del catálogo y restablecer contraseña con confirmación; herramientas en `POLITICAS_DEL_PORTAL` de `ai_chat/tool_execution/politica.py`. Textos en los 8 idiomas del portal.
- **Pruebas**: `tests/test_sd_mercado_2026_11.py`, `tests/test_sd_mercado_canales_2026_11.py` (Slack y WhatsApp con dobles de `httpx`), `frontend/src/i18n/__tests__/sdMercado.test.ts`. Sin ejecutar.

## Traducción en tiempo real (16-11-2026)

Revisión de base de datos **175** (`alembic/versions/175_traduccion_en_tiempo_real.py`, sobre la 174, con downgrade). Uso en `docs/SERVICE_DESK.md` (misma sección); despliegue en `docs/DESPLIEGUE.md` (B.1 y B.2).

Un operador que habla castellano lee en castellano lo que un cliente le escribe en chino, y lo que contesta le llega al cliente en chino.

- **Servicio** (`app/services/traduccion/`): `servicio.traducir()` es el único camino. Pasos: empresa y canal activados (`TRANSLATION_ENABLED`, `TRANSLATION_CHANNELS`) → idioma de origen (el dado, el guardado o la detección local si es segura) → caché por (texto, origen, destino, glosario) → tope de gasto de IA de la empresa → proveedor por lotes → caché y registro de uso. Si falla, devuelve `unavailable` con el motivo y se muestra el original con aviso. Nunca devuelve una traducción a medias: si falla un lote, no se usa nada de él.
- **Proveedores intercambiables** (`proveedores/`, interfaz `ProveedorDeTraduccion`, registro `FABRICAS`):
  - `ai`, por defecto: el proveedor de IA de la empresa vía `call_ai`, módulo `translation`, que se puede enrutar en el Hub de IA. Hereda la gobernanza, el registro de uso y el tope diario. Las instrucciones van en inglés, se construyen con el idioma destino y piden JSON.
  - `deepl` y `azure`: credenciales **cifradas de cada empresa**, sin respaldo global ni del entorno (`credenciales_de_la_empresa`). La salida es https, con timeout `OUTBOUND_HTTP_TIMEOUT_SECONDS` y protección SSRF (`cliente_httpx`). Su uso se apunta en `AIUsageLog` (módulo `translation`). Cuentan para el tope si se fija `TRANSLATION_COST_PER_MILLION_CHARS_USD`, y respetan el tope en todo caso.
- **Detección** (`idiomas.py`, `deteccion.py`): es local y sin red. Mira el sistema de escritura y, en alfabeto latino, las palabras funcionales. Se hace en `before_flush` en todo comentario, ticket o mensaje de canal nuevo, venga de donde venga: portal, correo IMAP/M365, chat, WhatsApp, Slack, asistente o agentes. Si no es segura (`TRANSLATION_DETECT_MIN_CONFIDENCE`), el idioma lo pone el proveedor al traducir.
- **Entrada** (`mensajes.py`, `POST /translation/messages`): cada mensaje se ve en el idioma de quien mira y se guarda en `message_translations` (una fila por mensaje, campo e idioma, con proveedor, autor y fecha). Dos operadores con idiomas distintos tienen cada uno el suyo, y la segunda vez no se paga. El acceso es el de la pantalla: `get_scoped_ticket_or_404`, la empresa de la conversación y `assert_conversation_access` en el chat interno. Las notas internas se traducen solo entre operadores.
- **Salida** (`salida.py`):
  - El idioma del cliente se toma, por este orden, del contacto, del portal (el del chat o el por defecto del portal de su empresa) y del detectado.
  - `POST /translation/outbound/preview` da una vista previa editable.
  - `client_text`/`client_language` en `POST /sd/tickets/{id}/comments` y en `/sd/channels/conversations/{id}/reply` mandan la versión del cliente. El cuerpo guardado es lo que recibe el cliente, y lo que escribió el operador queda con `origin=author`.
  - Sin vista previa (Slack, API), la respuesta se traduce sola si `TRANSLATION_OUTBOUND_AUTO`.
  - Con `TRANSLATION_INCLUDE_ORIGINAL`, el cliente ve también el original debajo: en el portal, en el correo de aviso, en el chat y en WhatsApp.
  - Cada envío traducido queda en la auditoría (`TRANSLATE`: idiomas, proveedor, `origin=auto|edited`).
  - Los avisos por correo a los agentes llevan el comentario en el idioma de cada agente.
- **Notas internas**: nunca pasan por la salida, aunque se manden con `client_text`.
- **Glosario** (`glosario.py`, `/translation/glossary`): términos que no se traducen o que se traducen siempre igual. Se aplican así:
  - Al modelo de IA le llegan en las instrucciones.
  - En DeepL y Azure se marcan (`<x>` o `notranslate`) para que no se traduzcan.
  - Solo cuentan en la huella de la caché los términos que aparecen en el texto.
- **Base de conocimiento** (`kb.py`, `/translation/kb/{id}`):
  - Se generan versiones en los idiomas del portal (`sd_kb_article_translations`) que nacen **en revisión**. Las publica o rechaza un revisor (`puede_publicar`).
  - El portal (`/sd/kb`, `/sd/kb/suggest` y `/sd/kb/{id}`, con `?lang=`) sirve la versión publicada en el idioma del cliente. El bot del chat en vivo también.
- **Chat interno y editor**: traducción bajo demanda (`chat_message` y `POST /translation/text`). `/traducir` del `AIInlineEditor` traduce a cualquier idioma con el servicio, sin prompt fijo ni emojis.
- **Asistente del portal**: entiende el mensaje del cliente también en el idioma de la empresa, y devuelve los títulos de los tickets y los nombres de los servicios en el idioma del cliente.
- **Textos del sistema** (`textos_del_sistema.py`): los tickets automáticos de ALM (renovación, avería, devolución, petición y compra) guardan la plantilla (`sd_tickets.system_template`/`system_params`). Se escriben en el idioma de quien los pide y cada operador los lee en el suyo, sin proveedor (`origin=system`). Las plantillas están en los 8 idiomas del portal.
- **Ajustes** (grupo `traduccion`, en caliente): `TRANSLATION_ENABLED` (por defecto **activada**; cada empresa puede apagarla y entonces no sale ningún texto a un traductor), `_PROVIDER`, `_CHANNELS`, `_OUTBOUND_AUTO`, `_INCLUDE_ORIGINAL`, `_DETECT_MIN_CONFIDENCE`, `_MAX_BATCH_CHARS`, `_AI_MAX_TOKENS`, `_COST_PER_MILLION_CHARS_USD`, `_CACHE_RETENTION_DAYS` (tarea `purgar_cache_de_traducciones`, diaria a las 03:25) y `_KB_LANGUAGES`.
- **Interfaz**:
  - Administración: Ajustes → Sistema → Traducción (`TraduccionSection.tsx`), con uso, ajustes, credenciales, prueba y glosario.
  - Ticket (`TicketDetail.tsx`) y bandeja de canales (`BandejaDeCanales.tsx`): `TextoTraducido` (con «Traducido automáticamente» y «Ver original») y `VistaPreviaDeSalida`.
  - KB: `VersionesKbPanel` en `ITSMKnowledgeTab`.
  - Chat interno: `ChatPage`.
  - Portal: `lang` en las llamadas a la KB.
  - Los nombres de idioma salen de `Intl.DisplayNames`.
- **Pruebas** (escritas, **sin ejecutar**):
  - Backend: `tests/test_traduccion_en_tiempo_real_2026_11.py`. Los proveedores se prueban **solo con dobles** (DeepL y Azure con doble de su salida HTTP, IA con doble de `call_ai`), nunca contra el servicio real.
  - Frontend (vitest): `frontend/src/__tests__/traduccion/*`, `TraduccionAdmin.test.tsx`, `VersionesKbPanel.test.tsx` y `portalKbIdioma.test.tsx`.
- **Pendiente**:
  - Las listas (colas de tickets, bandeja) muestran el título guardado, sin traducir.
  - El panel flotante del chat (`GlobalChatPanel`) no tiene «Traducir».
  - El editor de credenciales que se reutiliza arrastra textos fijos en castellano y un emoji, como la pestaña de credenciales que ya existía.
  - Los demás comandos del `AIInlineEditor` siguen con prompts en castellano.

## Proyectos — planificador, hub y vistas (16-11-2026)

Revisión de base de datos **173** (`alembic/versions/173_proyectos_planificador_y_hub.py`, sobre la 172). Una sola migración con downgrade y migración de datos de los duplicados.

### 1. Planificador real

- **Un solo modelo de dependencias.** `task_dependencies` (`app/models/bookings.py`) gana `link_type` (`schedule` planifica; `relates_to`, `duplicates`, `cloned_from` son informativos) y `note`. La tabla duplicada `task_dependency_meta` (`TaskDependencyMeta`) se migró y se borró: `blocks` → FS, `blocked_by` → FS al revés, el resto como vínculo informativo; un par que ya existía no se duplica. La API duplicada `/task-dependencies*` (issue_types) se retiró; queda `/tasks/dependencies` con `PATCH /tasks/dependencies/{id}` para tipo, desfase, vínculo y nota. Crear exige que las dos tareas existan y, si planifica, que sean del mismo proyecto y no cierren un ciclo.
- **Calendario laboral** (`app/services/planificador/calendario.py`): empresa = `PLANNING_WORKDAYS` + `DEFAULT_WORKING_HOURS_PER_DAY` + festivos sin `applies_to`; persona = el de la empresa menos sus ausencias **aprobadas**, con su jornada (`weekly_capacity_hours` / días laborables). No se usan aún los turnos ni los festivos por oficina (las personas no tienen oficina).
- **CPM** (`planificador/cpm.py`, puro): FS/SS/FF/SF con desfase (en laborables del calendario de empresa), duraciones en laborables del calendario de la persona (fechas si las hay; si no, horas / jornada; mínimo 1), restricciones `snet`, `mso`, `fnlt`, `mfo` (holgura negativa si no se llega), holgura total y libre, tareas terminadas fijas en sus fechas reales, ciclos detectados y devueltos sin romper el cálculo.
- **Resultado guardado en la tarea** (`tasks.early_*`, `late_*`, `total_float_days`, `free_float_days`, `is_critical`, `schedule_computed_at`) sin tocar `updated_at`. Se recalcula al crear/editar tareas (fechas, horas, persona, estado, restricción), mover barras, crear/editar/borrar dependencias y en la cascada (ajuste `PLANNING_AUTO_RECALCULATE`). `/tasks` devuelve además `baseline_start`/`baseline_end` de la línea base vigente (dos consultas por página) y `progress_pct`/`constraint_*`.
- **Cascada** (`tasks/scheduling.py`): los cuatro tipos con la misma regla que el CPM (`cpm.inicio_minimo`), calendarios, solo empuja, conserva la duración laborable; la ruta comprueba antes la tarea del usuario.
- **Líneas base**: foto por tarea en `gantt_baseline_tasks` (con coste planificado), `is_current` (una vigente por proyecto; la migración pasó los JSON a filas y dejó vigente la más reciente), `POST …/make-current`, comparación contra hoy o contra otra (`?against=`), auditadas.
- API: `GET /planning/projects/{id}/schedule`, `POST …/schedule/apply` (Replanificar). `GET /activity/projects/{id}/critical-path` responde con lo mismo (el CPM antiguo de `activity_service/planificacion.py` se borró; un proyecto sin tareas da plan vacío, no 404).
- UI: bajo el Gantt (con proyecto), pestañas Camino crítico, Dependencias, Líneas base y Nivelación (`components/planificador/*`); el tooltip del Gantt enseña la holgura y las flechas solo son vínculos que planifican.

### 2. Ficha de proyecto como hub

`ProjectDetailPage.tsx` tiene una lista de pestañas (`PestanaDeFicha`: id, etiqueta, icono, visibilidad, `render`): Resumen, Tareas (vistas de trabajo), Gantt, Sprints, Presupuesto y finanzas, Valor ganado, Hitos y facturación, Equipo, Riesgos, RACI, UAT, IA, Documentos, Lecciones y Recursos técnicos (la de licencias). Gantt, Sprints, RACI, UAT e Hitos son las páginas globales con la prop `projectId` (proyecto fijo, sin selector), cargadas en diferido. Botón «Guardar como plantilla».

### 3. Vistas de trabajo

`components/planificador/VistasDeTrabajo.tsx` en Tareas (junto a Kanban y Lista) y en la ficha: tabla editable en línea (título, estado, persona, prioridad, horas, avance, fechas; columnas elegibles), línea temporal (barra crítica y de línea base), calendario mensual y carga por persona (`GET /planning/workload`, `planificador/carga.py`, calendario de cada persona). **Vistas guardadas**: modelo único `saved_filters` (antes solo filtros NQL de `/epics/filters`) con `view_type`, `config`, `project_id`; API `GET/POST/PATCH/DELETE /planning/views` (propias y compartidas; compartir es de admin/PM).

### 4. Recursos

- **Nivelación real** (`planificador/nivelacion.py`): carga diaria de cada persona con todas sus tareas (de cualquier proyecto), capacidad = jornada × `LEVELING_OVERALLOCATION_PCT`; retrasa tareas no críticas del proyecto dentro de su holgura comprobando cada sucesora (cuatro tipos y desfase), restricciones y fin tardío; nunca alarga el proyecto. `GET /planning/projects/{id}/leveling` propone sin escribir; `POST …/leveling/apply` recalcula en el servidor y aplica todas o las elegidas (auditado).
- Pantalla **Planificación de recursos** (`/resources/planning`): disponibilidad (carga por semana), skills del equipo y quién está libre por skill, alertas con «marcar como vista», histórico de utilización y nivelación.

### 5. Valor ganado único

`app/services/evm_service.py`: BAC de la línea base vigente (coste planificado) o del presupuesto; PV repartido por los laborables de cada tarea en la línea base (sin ella, plan de hoy; sin fechas, ventana del proyecto); EV = presupuesto de cada tarea × su avance real (`progress_pct`, terminada 100 %, sin valor el peso de su estado). `project_service.evm`, `portfolio_service.get_evm_quick` (que ya usaba la ficha) y `profitability_service._indicadores_evm` llaman a este cálculo. Curva S: `evm_snapshots`, un punto por proyecto y día (`app.worker.guardar_puntos_de_curva_s`, 02:25, por organización, `EVM_SNAPSHOTS_ENABLED`); `GET /planning/projects/{id}/evm[/curve]`, `POST …/evm/snapshot`. Pestaña «Valor ganado» con KPIs y curva.

### 6. Cartera: intake → puntuación → fases → proyecto

Tablas `portfolio_criteria` (peso, inverso), `portfolio_gates` (orden, flujo de aprobación, mínimo) y `portfolio_proposals`. `app/services/cartera_service.py` y `/portfolio-intake/*`. La fase la decide el motor de aprobaciones (tipo `portfolio_gate` en `approval_engine/fuentes.py`, con el flujo de la fase o el por defecto, políticas incluidas); sin flujo, admin/PM en pantalla. Mínimo de puntuación: el de la fase o `PORTFOLIO_MIN_SCORE_TO_ADVANCE`. Aprobada, se convierte en proyecto (con plantilla si la tiene) y entra en su cartera. Capacidad: horas pedidas por rol frente a las libres del equipo en la ventana. Pantalla `/portfolio/intake`.

### 7. Plantillas unificadas

Un servicio, `app/services/plantillas_de_proyecto.py`: listar, crear (fases, tareas con rol y duración, **dependencias** `template_task_dependencies`, roles, documentos, riesgos, entregables), aplicar (crea todo y planifica con el CPM), instanciar y crear desde proyecto. `billing_reports_service/plantillas.py` y `advanced_config_service/plantillas.py` delegan; `POST /projects/{id}/export-template` dejó de devolver `tpl-123`. API canónica `/templates` (la que usa la pantalla). Datos: la migración asigna a cada tarea de plantilla el rol cuya skill coincide.

### 8. IA en pantalla

Pestaña IA de la ficha (`PanelIaDelProyecto`): salud y riesgo de retraso (`/activity/projects/{id}/health`), simulación what-if (`…/simulate`), estimación de horas (`/ai-planning/estimate/{tarea}`, aceptar la registra) y persona sugerida (`/semantic/suggest/task`), aplicables tarea a tarea.

### Otros

- RACI ya no se monta dos veces (fuera el alias `/raci/*`).
- Ajustes nuevos (grupo `proyectos`): `PLANNING_WORKDAYS`, `PLANNING_CRITICAL_FLOAT_DAYS`, `PLANNING_NEAR_CRITICAL_FLOAT_DAYS`, `PLANNING_AUTO_RECALCULATE`, `LEVELING_OVERALLOCATION_PCT`, `LEVELING_HORIZON_DAYS`, `RESOURCE_UNDERUSE_PCT`, `RESOURCE_AVAILABILITY_WEEKS`, `EVM_SNAPSHOTS_ENABLED`, `EVM_CURVE_MAX_POINTS`, `PORTFOLIO_MIN_SCORE_TO_ADVANCE`.
- Textos en `planificador.*`, `cartera.*` y `nav.*` (es/en/zh).
- Tests: `tests/test_planificador_cpm.py`, `tests/test_planificador_servicio.py`, `tests/test_evm_cartera_plantillas_173.py`, `frontend/src/__tests__/planificador.test.tsx`; ajustados `test_v24_features.py`, `test_profitability_pnl.py`, `test_baselines_y_costes_por_tenant.py`.

## Pasada de diseño (16-11-2026)

Todas las pantallas siguen el estándar de `/projects`, `/absences`, `/cmdb` y `/m365`: `PageShell` + `PageHeader` con icono lucide y el título del menú (`nav.*`), acción principal en la cabecera (`Button` con icono `Plus`, sin «+ » en el texto), filtros en una barra bajo la cabecera, contenido a todo el ancho, `Tabs` del kit, `KpiCard` en `.ds-grid-stats`, `EmptyState` con icono lucide, `StatusBadge`, solo tokens de `index.css` (activo = `--accent`), nada de emojis (código ni diccionarios), textos en es/en/zh sin anglicismos ni jerga técnica (.env, variables, rutas de API) y fechas con `fmtDate`/`fmtDateTime`/`formateadorDeFecha`.

### Kit común (components/ui) — impone el estándar

- `KpiCard`: una sola forma (la de /projects): cifra sin monoespaciado, etiqueta en versalitas debajo, icono lucide pequeño; un icono emoji se ignora; sin borde ni fondo de color; nueva prop `onClick` (+ `ariaLabel`).
- `EmptyState`: ya no pinta emojis/textos como icono (sale el icono neutro `inbox`, aviso en desarrollo); iconos por clave pasados a lucide; el `ctaLabel` es un `Button` con `Plus`. `DataTable` usa `inbox` por defecto (antes «○»).
- `Tabs`: siempre pastilla `md` (`variant`/`size` se ignoran) y sin emojis en etiquetas de texto.
- `Button`: «+ texto» → icono `Plus`; emojis del texto fuera; `subtle` se pinta como `secondary`; reenvía `aria-*` y `data-*`; mismo alto que `Input`/`Select` (`md` = 38 px).
- `Input` (`maxLength`, `autoFocus`, `inputMode`, `disabled`, `min/max/step`), `Select` (`disabled`, `required`, `aria-label`, `placeholder`, `false` quita la opción vacía), `FormField` (icono `AlertTriangle` en vez de «⚠»), `ViewToggle`/`SearchInput`/`IconFR`/`IconCR` con lucide. Guía: `components/ui/DESIGN_SYSTEM.md`.

### Pantallas A–L, /chat, editor IA y portal

- **A–C**: `/agent-dashboard`, `/ai-hub` (sin `AI_DAILY_BUDGET_USD` ni «.env»; ámbitos y acciones traducidos), `/alerts` (+ `SmartAlertsPanel`), `/alm` (9 KPIs a `KpiCard`, sin barra de una sola pestaña), `/approvals` (sin barra de una pestaña; «Nuevo flujo» en cabecera; entidades con lucide), `/ask-company` (cabecera con icono), `/automations` (sin «+ +»; filtro segmentado → select), `/bpm` (Catálogo/Ejecución con `Tabs`; sin borde azul de foco tras clic), `/budgets` (KPIs estándar, sin variables `BUDGET_*` en ayudas), `/calendar`, `/capacity` (acción en cabecera), `/changelog` («Registro de cambios»), `/changes` (un solo nivel de pestañas), `/clients` (+ ficha y usuarios del portal; vacíos lucide; fechas formateadas), `/cmdb` (+ grafo; iconos de clase de CI en `components/cmdb/iconosCi.tsx`), `/contracts`, `/contracts-ai` (selector de PDF con botón), `/cumulative-flow` (sin `POST /epics/cfd/snapshot`), `/custom-fields`.
- **D–E**: `/data-explorer` (constructor visual sin cortes, «Preguntar a los datos», fechas de la app), `/data-governance` (un solo estilo de pestañas; valores RGPD traducidos), `/data-platform`, `/deliverables`, `/dependencies`, `/developer` (sin ancho centrado), `/documents` (botón del vacío = «Subir documento»; categorías traducidas), `/enterprise` (menú «Integraciones y seguridad»; altas en la cabecera), `/epic-gantt`, `/epics` («Hoja de ruta»), `/esign` (sin ancho centrado ni emoji), `/evm` (vacío con `EmptyState`), `/executive` («Panel ejecutivo», cabecera a todo el ancho), `/expenses` («Nuevo gasto» en cabecera).
- **E–L**: `/exports` (sin `JIRA_ENABLED … .env`), `/finance-dashboard`, `/gantt` (`<Page>` estándar, filtros en barra), `/git` (sin rutas `/api/v1` ni secretos `.env`), `/governance` (sin `POST /api/v1/mcp` ni `MCP_WRITE_MODE`), `/grc` («Registro de auditoría»), `/import` (selector de fichero con botón), `/imputar` (sin ancho de 680 px), `/inbox` (Notificaciones sin segunda cabecera: prop `embedded`), `/invoices`, `/issue-types`, `/jira-integration` («incidencias»; tarjetas desactivadas legibles), `/lessons`, `/absences` (fechas con el formateador), `/intake/:token`.
- **/chat** y panel flotante `GlobalChatPanel`: cabecera estándar con «Nueva conversación», sin «# #» (se quita el `#` del título que manda el backend), vacíos `EmptyState`, textos fijos a es/en/zh; el panel detecta los mensajes propios por `user_id` (antes `author_id`, que el backend no manda). El selector de reacciones mantiene emojis: son contenido.
- **`AIInlineEditor`**: completar/resumir/mejorar/puntos mandan las instrucciones a la IA en inglés, pidiendo la respuesta en el idioma del texto (o el de la interfaz), como /traducir.
- **`components/DocumentsPanel.tsx`** (proyecto, tarea, ticket): `Button`/`IconButton`, `EmptyState`, categorías y estado de aprobación traducidos con iconos lucide.

Tests: `frontend/src/__tests__/disenoSinEmojis.test.ts` (sin emojis en el código de A–L, /chat, editor IA y kit, ni en los textos es/en/zh que usan) y `frontend/src/__tests__/kitDiseno.test.tsx` (lo que impone el kit).

### Pantallas M–Z

- **M–O**: `/meetings-ai`, `/mfa` (sin ancho centrado), `/milestone-billing` («Facturación por hito», «milestone» → «hito»), `/my-equipment`, `/nexus-agent` (sin nombres técnicos de herramientas ni «(.env)» visible), `/nps` (fuera `--surface-5` como color de texto), `/okrs` (filtros fuera de la cabecera, años calculados), `/oracle` (valores crudos traducidos), `/org-chart` (subtítulo correcto), `/organizations`, `/performance-reviews` («Evaluaciones de desempeño»), `/pipeline` («Tasa de éxito»).
- **P–R**: `/portfolio` y `/portfolio/intake` (cabecera estándar), `/predictions` (sin botones naranja/rojo, métodos y niveles traducidos en el módulo nuevo `prediccion_bi`), `/profitability`, `/project-permissions`, `/project-templates`, `/projects` (título `nav.projects`), `/projects-dashboard` («Panel de proyectos», periodo con `Tabs`), `/public-forms`, `/raci`, `/rate-cards` («Tarifas», el detalle ya tiene cabecera), `/report-builder` (botones desactivados legibles en oscuro), `/reports` (pestañas bajo la cabecera, aviso de correo sin `SMTP_*`).
- **R–S**: `/resource-forecast` («Previsión de recursos», semanas legibles), `/resource-scheduler` (`PageShell` en vez de contenedor propio), `/resources` y `/resources/planning`, `/revenue` (una sola fila de KPIs), `/risk-scores`, `/risks`, `/scenarios`, `/semantic-engine` («Asignación IA»), `/settings` (Puesta en marcha y secciones avanzadas en lenguaje llano, sin `.env`, `SMTP_HOST`, `SD_INBOUND_ADDRESS` ni claves internas; 29 grupos de parámetros traducidos), `/settings/policies`, `/settings/project-workflows`.
- **S–W**: `/skills` («Habilidades»), `/sla-calendars`, `/sprint-charts`, `/sprint-planning`, `/sprints`, `/subcontractors` (el detalle ya tiene cabecera), `/support-dashboard`, `/tasks` (vista con `Tabs`; `SmartScheduleModal` traducido), `/team-dashboard`, `/time` (cabecera arriba y pestañas debajo), `/timer`, `/training`, `/uat`, `/user-costs`, `/webhook-log` («Registro de webhooks»), `/wiki`, `/work-dashboard` (fecha con el formateador, sin «Imputar horas» duplicado, sin «100 %» sin tareas).

### Service desk, /sd/* y comunes

- `/support-dashboard` → `MetricsDashboardTab`: sin cabecera ni `PageShell` anidados, periodo con `Tabs`, `KpiCard`; con 0 tickets el SLA muestra «—» (antes 100 % «Excelente»).
- `/sd/workflow-designer`: título del menú («Diseñador de flujos de soporte»), «blueprint» → «flujo», nodos con lucide, ramas y tipo de entidad traducidos.
- Configuración del service desk (`ConfigTab` y `Config*`): `Tabs`, títulos sin anglicismos, ayudas de canales y correo sin jerga técnica.
- Bandeja de canales y catálogo: conversación/servicio seleccionado con `--accent`; `Tabs` estándar.
- Cambios, problemas, errores conocidos y base de conocimiento: `Tabs`, `StatusBadge`, fechas con el formateador; `ChangeRolloutPanel`, `Cmdb3dGraph` y `RcaWizardModal` traducidos (antes castellano fijo).
- `components/dashboard/DashKit.tsx`: su `KpiCard` delega en el del kit, `DashEmpty` en `EmptyState`, «últimos N días» por `t()`.
- Ajustes → Traducción (`TraduccionSection`): nunca muestra claves `TRANSLATION_*`.

### Test

`frontend/src/__tests__/disenoMZSinEmojis.test.ts`: falla si vuelven emojis al código (sin contar comentarios) de estas pantallas o a sus textos en es/en/zh, o si un texto empieza por «+ ».

### Pendiente

- Backend: `app/services/ai_provider_service/resolucion.py:42` genera «proveedor (.env)»; el frontend lo oculta en `/nexus-agent`, pero se ve en `/ai-hub` y `/governance`.
- ~~Kit (`components/ui`): `Select` sin `disabled` y con opción vacía fija; `Input` sin `maxLength`/`autoFocus`/`inputMode`; `Button` sin `aria-expanded`; `FormField` pinta «⚠» en los errores.~~ Resuelto (ver «Kit común»).
- `TimePage.css` presenta como cabecera de pestaña las de `ImputarPage`/`TimesheetsPage` con clases internas de `PageHeader` (frágil); `/imputar` mantiene su ancho de 680 px.
- Iconos que escribe el usuario y se guardan (tipos de tarea, estados de flujo, categorías del catálogo) siguen admitiendo emoji: es dato, no interfaz.
- `components/servicedesk/sdMercado.css` usa tokens que no existen (`--color-background-warning`…).
- CSS muerto en `DashKit.css` y `ReportsPage.css` (`rep-*`).

## Portal en 8 idiomas (16-11-2026)

Regla: la interfaz de operadores va en es/en/zh (`i18n/langs/*.mjs`); el portal de clientes en 8 (es, en, fr, de, pt, it, pl, zh: `i18n/portal/*.ts`) y todo su texto visible sale de esos 8.

### Qué cambió

- **Un solo traductor en el portal**: `useLang()` (`pages/portal-client/portalClientContext.tsx`) lee `i18n/portal/*` y acepta variables (`t('clave', { n })` rellena `{{n}}`). Ningún fichero del portal (`pages/portal-client/*`, `PortalClientePage.tsx`, `PortalPublicViewPage.tsx`) usa ya `useAppT`/`useAppLang`/`etiquetaCodigo`.
- **Claves migradas**: 409 claves que el portal leía del diccionario de operador (`portal_perfil.*`, `portaldashboard.*`, `portaladvanced.*`, `portalsupportdesk.*`, `portalsurveys.*`, `portalaichatwidget.*`, `portalkb.*`, `portalui.*`, `portalcliente.*`, `portalclientcontext.*`, `portal_public.*`, `governedconversations.*` y sueltas de `common.*`, `chat.*`, `nav.*`…) están ahora en los 8 diccionarios del portal **con el mismo nombre** (`modulo.clave`), traducidas a fr/de/pt/it/pl; `{x}` pasó a `{{x}}`. Las que ya no usaba nadie se borraron de `langs/*.mjs` en la segunda pasada (ver «Restos cerrados»).
- **GovernedConversations** (bandeja compartida): `useTextoConversacion(mode)` elige el traductor — `mode="client"` (portal) usa el del portal; `mode="team"` (vista interna) el del operador. Las claves se llaman igual en los dos sistemas. El panel de políticas (`ConversationPoliciesPanel`) es solo de operadores y sigue con `useAppLang`.
- **Estados y prioridades**: el portal ya no enseña `status_label`/`priority_label`/`cr_status_label` del servidor (en castellano): pinta `st_<código>` y `prio_<código>`. Nuevas: `st_planning`, `st_paused`, `st_archived`, `st_blocked`, `st_skipped`, `st_expired`, `st_wontfix`, `st_deferred`, `st_under_review`, `st_implemented`, `prio_p1_critical`…`prio_p4_low`. `useEtiquetaEstado` ya no cae a la etiqueta castellana de `STATUS_CFG`.
- **Fechas y números**: `fijarIdiomaDeFormato(lang)` (`utils/helpers.ts`) hace que `fmtDate`/`localeActivo`/`fmtRelative` usen el idioma del cliente mientras el portal (o la vista pública) está montado; `fmtRelative` tiene locales date-fns de los 8.
- **Vista pública por enlace** (`/portal/view/:token`): usa los diccionarios del portal con el último idioma del portal en ese navegador o el del navegador (si es uno de los 8).
- **Error genérico**: `GENERIC_ERROR_FALLBACK` («Error inesperado») se cambió en el portal por la clave `error_inesperado`.
- **Sin banderas**: `PORTAL_LANGUAGES` ya no tiene `flag`; la pantalla de textos del portal (`SettingsAdvancedSections`) muestra código y nombre. El perfil del portal usa `PORTAL_LANGUAGES` en vez de una lista copiada.
- **Textos de servidor**: los tickets que abre el sistema (`system_template`, plantillas en 8 idiomas de `app/services/traduccion/textos_del_sistema.py`) se devuelven al portal en el idioma de la ficha del cliente (`textos_del_sistema.en_idioma`, usado por `GET /sd/tickets/client/my` y `/sd/tickets/client/{id}`). La KB ya llegaba en el idioma del portal (`?lang=`).
- Se corrigieron `dashboard_welcome` y `dashboard_days_remaining` en fr/de/pt/it/pl/zh, que habían perdido `{{name}}`/`{{n}}`.

### Tests

- `frontend/src/i18n/__tests__/portalOchoIdiomas.test.ts`: mismas claves y mismas `{{variables}}` en los 8 diccionarios; toda clave que usa el portal existe en los 8; ningún fichero del portal llama al traductor de operador; en `GovernedConversations` solo `useTextoConversacion` (y el panel de políticas) lo usan.
- `tests/test_portal_ocho_idiomas_2026_11.py`: plantillas del sistema en los 8 idiomas y `en_idioma`.

### Restos cerrados (16-11-2026, segunda pasada)

**1. Kit y aviso global en el idioma del portal.** `components/ui/useTextoUi.ts` tiene ahora un contexto de textos de interfaz: `TextosDeInterfazProvider` (`t`, `lang` y, opcional, `errorDelServidor`). `useTextoUi()`/`useIdiomaUi()` usan el del proveedor que los envuelva y, si no hay, el traductor de operador como antes. El portal envuelve su árbol con `TextosDeInterfazDelPortal` (`portalClientContext.tsx`; en `PortalClientePage` y `PortalPublicViewPage`), que da el traductor del portal. `Pagination`, `Confirm` y `ProjectRiskBadge` pasaron de `useAppLang`/`useAppT` a `useTextoUi`. El aviso global (`ToastContext`, montado por encima de todo) usa `useTextosUiGlobales()`: el último `TextosDeInterfazProvider` montado se apunta en una pila y, mientras el portal está en pantalla, «no se pudieron cargar los datos», «error inesperado» y «cerrar aviso» salen en su idioma. Claves del kit (`uikit.*`, `pagination.*`, `toast.*`, `common.confirm`, `colvisibility.fijo`, `fecha.*` del selector de fecha) añadidas a los 8 diccionarios del portal con el mismo nombre (`{{x}}` en las que rellena el kit; `fecha.min`/`fecha.max` llevan `{fecha}` con una llave porque las rellena el propio selector). Fuera del portal nada cambia.

**2. Errores del servidor con código.** `ErrorDeDominio` acepta `code` y `params`; el manejador de `app/main.py` los añade a la respuesta: `{"detail": <castellano, como antes>, "code", "params"}`. Catálogo en `app/core/codigos_de_error.py` (`MENSAJES`, `error(status, codigo, **params)`, `ErrorConCodigo` —un `ValueError` con código para los servicios que ya lanzaban `ValueError`— y `desde_valor(status, e)` para los endpoints). Mismo patrón que `bpm` (`error_code` + `error_params` junto al texto) sin cambiar `detail`, que siguen leyendo el operador y los clientes de la API. Con código: `client_portal_service/*` y sus endpoints (`/portal/*`: sesión, login, perfil, documentos, facturas, solicitudes, UAT, wiki, encuestas), `portal_conversation_service/*` (`/portal/conversations`), y del Service Desk lo que ve el cliente: ticket del cliente (detalle, comentario, CSAT, alta en proyecto ajeno), chat en vivo (`conversaciones.py`, `canales.py`) y asistente del portal. El portal lo traduce con `err_srv.<código>` (46 claves en los 8 diccionarios): `useErrorDelPortal()` sustituye a `extractErr` en las pantallas del portal (y en `GovernedConversations` con `mode="client"`) y el aviso global traduce los errores de carga con código (`utils/mensajeDeError.ts`).

**Comentarios automáticos.** `sd_ticket_comments.system_template`/`system_params` (migración `177_portal_idiomas_restos`, sobre `175_traduccion_en_tiempo_real`: no existía `176_periodo_libre` al crearla). Plantillas en `textos_del_sistema.COMENTARIOS` (8 idiomas, sin emojis): resolución automática y sugerencia de la IA (`ai_auto_resolution_service`) y escalado (`ticket_ops_service`, nota interna). Se guardan en el idioma del solicitante (público) o de la empresa (interno) y `en_idioma()` los vuelve a pintar en el idioma de la ficha del cliente en `/sd/tickets/client/*`, con `author_type="system"` (el portal pone «Sistema» como autor). Los comentarios de aprovisionamiento y de los playbooks del agente autónomo llevan texto escrito por operadores: salen en el idioma del cliente por el mismo camino que una respuesta pública sin vista previa (`salida.publicar_texto_del_operador` → `preparar` + `anotar_autor`).

**3. Contenido de operadores en el idioma del cliente.** `app/services/traduccion/contenido_del_portal.py` (`localizar`, `idioma_del_lector`) traduce al leer, con el servicio de siempre (canal nuevo `portal` en `TRANSLATION_CHANNELS`, por defecto activo; pantalla de traducción con su etiqueta en es/en/zh): avisos (`GET /sd/announcements`), páginas de la wiki del portal (`GET /portal/wiki/pages[/{id}]`) y nombres y descripciones del catálogo (`GET /sd/catalog`, categorías y servicios). Solo para el cliente del portal (el operador lee el original), al idioma de la pantalla (`?lang=`, que ya manda el portal) o de su ficha. Respeta que la empresa traduzca y tenga el canal, la caché por idioma (se confirma aunque la petición sea de lectura, para no volver a pagar) y el tope de gasto; desactivada, agotada o con fallo del proveedor, el original. Lo traducido lleva `translated_from` y `language`.

**4. Claves de operador borradas.** Con un script sobre todo `frontend/src` (sin contar `i18n/langs` ni `i18n/portal`) se comprobó qué claves de `portal_perfil`, `portaldashboard`, `portaladvanced`, `portalsupportdesk`, `portalsurveys`, `portalaichatwidget`, `portalkb`, `portalui`, `portalcliente`, `portalclientcontext` y `portal_public` usa algo que no es el portal: solo `portalsupportdesk.creado` (`BiGdprPanel`) y `portalsupportdesk.tu_respuesta` (`RcaWizardModal`), que se quedan. Se borraron 290 claves por idioma (es/en/zh). `frasesConVariables.test.ts` ya no cita las dos frases del portal (sus variables las comprueba `portalOchoIdiomas.test.ts`). `governedconversations.*` sigue: la usa la vista interna.

### Tests (segunda pasada)

- `frontend/src/__tests__/kitEnElIdiomaDelPortal.test.tsx`: Spinner, Pagination y Confirm dentro del portal en su idioma; fuera, el de operador; el aviso global (botón de cerrar, error de carga con código y sin él) en el idioma del portal; `mensajeDeError` con código, sin código y sin traductor. `Confirm.test.tsx` ajustado (simula `useAppLang`).
- `tests/test_portal_idiomas_restos_2026_11.py`: catálogo de códigos y `err_srv.*` en los 8 diccionarios; login, ticket y encuesta con código; un error sin código no cambia; plantillas de comentario en 8 idiomas y repintado; resolución por IA guardada en el idioma del solicitante y servida en el de la ficha; avisos, catálogo y wiki traducidos con un doble del proveedor, con caché, y el original si la traducción o el canal están desactivados o lee un operador.

### Restos cerrados (16-11-2026, tercera pasada)

**1. Errores con código que faltaban** (10 códigos nuevos en `codigos_de_error.MENSAJES`, con `err_srv.*` en los 8 diccionarios; `detail` igual que antes):
- `/portal/collaboration/*` (`services/collaboration/portal.py`): `sin_acceso_conversacion`, `sin_acceso`, `conversacion_obligatoria`, `mensaje_no_encontrado`, `demasiados_mensajes` (`{segundos}`); en la vía única de envío (`messages.py`), «Conversación no encontrada» y el acceso del cliente llevan código. La pantalla de mensajes del portal ya avisa del fallo al enviar (`useErrorDelPortal`).
- Chat de IA del portal (`/portal/ai-chat` y `/ai-modules/portal-ai/chat`): `mensaje_obligatorio` (detail «message required») y `sesion_invalida` («Token inválido»); el interruptor y el tope de los módulos de IA (`core/modulos_ia.py`): `modulo_ia_no_activado`, `modulo_ia_desactivado`, `modulo_ia_limite_diario` (`{n}`). El aviso de tope de gasto del chat («El asistente ha alcanzado su límite…») sale en el idioma de la ficha del cliente (`textos_del_sistema.AVISOS`/`aviso()`, 8 idiomas).
- Formularios dinámicos y demás rutas con `get_current_portal_client`: `require_portal_client` da `sesion_invalida` (detail «Autenticacion requerida»). Esas rutas no tenían otros errores para el cliente; además, las **etiquetas** de los campos (`/sd/dynamic-forms/public?lang=`) se traducen como el resto del contenido del portal (las opciones no: son valores que se guardan).
- Asistente del portal: `politica.codigo_de_denegacion_del_portal()` da `(código, datos)` — `herramienta_sin_politica` (`{herramienta}`) o `acceso_denegado` —; `denegacion_del_portal()` sigue devolviendo el texto.

**2. Comentarios del sistema en la vista del operador.** `ticket_detail_payload` (`GET /sd/tickets/{id}`) los repinta con `textos_del_sistema.comentarios_en_idioma()` en el idioma del operador que mira (`mensajes.idioma_de_usuario`: sus preferencias o el de la empresa). La traducción bajo demanda (`mensajes._de_plantilla`) también pinta un `ticket_comment` con plantilla en el idioma pedido, sin proveedor (`origin=system`).

**3. Marca «Traducido automáticamente» en el portal.** `contenido_del_portal.localizar` guarda el texto original en `original` (`{campo: texto}`) junto a `translated_from`. Componente del portal `pages/portal-client/TraduccionAutomatica.tsx` (variante de `TextoTraducido`, mismos estilos `traduccion.css`, textos `traduccion_portal.*` en 8 idiomas): `TraduccionAutomatica` (marca + «Ver original» por elemento) y `MarcaDeTraduccion` (marca controlada). Puesta en avisos (inicio y autoservicio), catálogo y etiquetas del formulario de alta (un «Ver original» común: dentro de un selector no cabe una marca por opción) y wiki (marca en la lista; «Ver original» en la página). Wiki: el detalle devolvía el JSON de bloques como texto y el portal no podía pintarlo; ahora devuelve la lista (`contenido_de_wiki`) y se traduce bloque a bloque (los de código no); las páginas antiguas en texto plano siguen igual.

**4. `TRANSLATION_CHANNELS` guardado.** La migración 177 añade `portal` a cada valor guardado no vacío de `app_settings` que no lo tenga (sin duplicar; un valor vacío es «ningún canal» y se respeta); el downgrade lo quita.

**5. Personalizaciones del administrador en el kit.** `PersonalizacionesDelPortal` (`portalClientContext.tsx`) carga `/portal/branding` y da `PortalCustomContext` por encima de `TextosDeInterfazDelPortal` (en `PortalClientePage`: `ClientAuthProvider` → `PersonalizacionesDelPortal` → `TextosDeInterfazDelPortal`); antes se daba dentro de la aplicación y el kit y el aviso global no las veían.

### Tests (tercera pasada)

- `tests/test_portal_idiomas_ultimos_restos_2026_11.py`: códigos nuevos y sus `err_srv.*`; denegación del asistente con código; módulo de IA apagado; chat de IA sin mensaje; mensajes del portal (5 casos); sesión del portal sin token; comentarios del sistema repintados para el operador (unidad, endpoint y bajo demanda); avisos con `original`; wiki por bloques; etiquetas de formularios dinámicos; pasos de datos de la migración 177 (funciones y `app_settings` en SQLite); aviso de tope de IA en 8 idiomas.
- `frontend/src/__tests__/portalUltimosRestos.test.tsx`: marca y «Ver original»; sin traducción no hay marca; claves en los 8 diccionarios; personalizaciones del administrador en el kit (con el contexto y con `PersonalizacionesDelPortal`).

### Pendiente

- Versiones traducidas **revisables** de avisos y catálogo (como la KB): no se hicieron; se sirven con traducción automática en caché. Haría falta una tabla de versiones y su pantalla de revisión.
- El historial del chat de IA del portal guarda las respuestas tal cual: un aviso de tope de gasto ya guardado se ve en el idioma que tenía la ficha al escribirlo.
- Errores de validación de esquema (422 de FastAPI) siguen sin código (`detail` de FastAPI, en inglés).
- Downgrade de la 177: quita `portal` también a quien lo hubiera puesto a mano después (no se distingue).

## Periodo libre en informes (16-11-2026)

Petición: los informes ofrecían 1 semana, 30 días y 90 días; ahora se puede pedir cualquier intervalo entre dos fechas, con granularidad hasta la hora donde el dato la tiene.

**Contrato de la API (todos los informes migrados).** `desde`/`hasta` en ISO 8601 (`[desde, hasta)`; sin zona, en `tz` o en la zona del usuario → empresa → UTC), `granularidad` = `auto|hour|day|week|month`, `tz` (IANA), `comparar` (solo donde el informe lo soporta) y el alias histórico (`days`, `hours`, `lookback_days`, `period_days`, `days_back`, `date_from`/`date_to`, `from`/`to`, `period=daily|weekly|monthly`), así que los clientes actuales siguen funcionando. Sin `hasta` = ahora; un horizonte (`sentido="futuro"`: vencimientos, renovaciones) cuenta hacia delante y acepta `days=0` («solo hoy»).

**Piezas comunes.**
- `app/core/periodo.py`: dependencia `periodo(dias_por_defecto, granularidades, serie, comparable, sentido, alias_*)` → `Periodo` (UTC, zona, granularidad resuelta, `fecha_desde/fecha_hasta` para columnas `Date`, `anterior()`, `rellenar()`, `agrupar()`, `a_dict()`). `expresion_de_bucket(db, columna, p)` agrupa igual en PostgreSQL (`date_trunc` sobre `timezone(zona, col)`) y en SQLite (función `cf_periodo_bucket` registrada en la conexión, que ejecuta la misma `clave_de_bucket` de Python); `filtro_de_periodo(columna, p)`. Semana = lunes (ISO). Los alias se declaran con `Query(alias=...)`, así que valen nombres reservados (`from`, `to`).
- Errores 422 traducibles: `detail = {code: "periodo.<motivo>", message, params}` con `desde_mayor_que_hasta`, `rango_excedido`, `demasiados_puntos`, `hora_no_admitida`, `granularidad_no_admitida`, `granularidad_invalida`, `fecha_invalida`, `zona_invalida`, `dias_invalidos`. Frontend: `periodo_err.<motivo>` (es/en/zh).
- Ajustes en caliente, grupo `informes` (Admin → Configuración dinámica): `PERIODO_MAX_DIAS` (1830), `PERIODO_MAX_PUNTOS_HORA` (744), `_DIA` (1100), `_SEMANA` (530), `_MES` (240), `PERIODO_AUTO_MAX_PUNTOS` (120: `auto` elige la granularidad más fina admitida que no pase de esos puntos). `GET /api/v1/periodo/limites` los publica para el selector.
- Frontend: `hooks/usePeriodo.ts` (la query string `periodo`, `desde`, `hasta`, `granularidad`, `comparar`, con `prefijo` si hay varios, es la fuente de verdad: el enlace se comparte con el periodo puesto; `sentido: 'futuro'` para horizontes), `utils/periodo.ts` (accesos rápidos, `auto` idéntico al servidor, validación, `formatearTramo` para ejes), `components/ui/SelectorDePeriodo.tsx`. Los accesos móviles van como `days` y los de calendario solo con `desde`, para que la clave de React Query no cambie sola.

**Granularidad por hora.** Solo donde el dato es un instante: tickets y métricas del service desk, panel de agente, SOC y observabilidad de seguridad, ABAC, gobierno de IA, auditoría de BI y de empresa, deriva de CMDB, NPS, aprobaciones, rendimiento por agente, documentos. Sin hora (día de calendario; la API responde `periodo.hora_no_admitida` y el selector la muestra desactivada y explicada): imputaciones, rentabilidad, productividad, CFD (fotos diarias), costes y horizontes de ALM, recursos técnicos del proyecto, exportación de imputaciones, evolución del margen OLAP, `/bi/data/timesheets`, demanda de recursos del pipeline. Solo mes: exportación Excel/PowerPoint de BI. Solo semana: tendencia de utilización y horizontes de previsión de recursos.

**Selector de fecha propio del kit.** Ninguna fecha usa ya `<input type="date|datetime-local|time">` (pintaba el formato de la región del navegador): `CampoFecha`/`CampoRangoDeFechas` (`components/ui/SelectorDeFecha.tsx`, lógica en `utils/fechas.ts`) escriben y muestran con el formato del idioma de la app (es dd/mm/aaaa, en mm/dd/yyyy, zh aaaa年m月d日, deducido del formateador de la app), con máscara, validación, calendario propio con teclado y ARIA de grid, primer día de semana por idioma, mín/máx, hora 24 h y zona. `DateInput` y el `Input` del kit con `type="date|datetime-local|time"` lo usan por dentro sin cambiar su API. El portal pasa su idioma y sus textos (8 idiomas, `i18n/fechaPortal.ts`).

### Restos cerrados (16-11-2026, segunda pasada)

1. **`/analytics/olap/margin-evolution`** usa `periodo()` (día, semana o mes: la tabla de hechos `fact_imputations` es diaria; hora → `periodo.hora_no_admitida`). La consulta DuckDB agrupa con `date_trunc('<granularidad>', d.date)` formateado a la clave común (`YYYY-MM-DDTHH:MI`, semana ISO) y filtra por `fecha_desde..fecha_hasta` con parámetros; el respaldo agrupa en SQL con `expresion_de_bucket` y usa la sesión de la petición (filtro automático por empresa; solo filtra a mano por `org_id` si abre su propia sesión). La serie se rellena (`p.rellenar`): cada punto lleva `t`, `clave`, `granularidad`, `total_cost`, `active_projects` y `month` (`YYYY-MM`, compatibilidad). Sin periodo, los últimos `months` (12) meses naturales por mes, como antes. Antes el respaldo devolvía `month` como `YYYYMM` y DuckDB como `YYYY-MM`; ahora los dos igual. Frontend: `useOlapMarginEvolution(months, periodo?)` (ninguna pantalla lo usa aún).
2. **Horizontes de previsión de recursos.** `/resource-forecast/weeks`, `/users/{id}`, `/summary` y `/bookings/heatmap` aceptan `desde`/`hasta`/`days` con `sentido="futuro"`, por semanas (`semanas_del_periodo` en `app/services/resource_analytics.py`: lunes de la semana de `fecha_desde` a la de `fecha_hasta`, máximo 52 → `periodo.demasiados_puntos`, porque cada semana calcula la carga de cada persona). `weeks` y `from_date` siguen valiendo; cada respuesta trae `periodo`. `/activity/pipeline/resource-demand` acepta el periodo y `horizon_months` como alias; **el horizonte no filtraba nada** (la fecha se calculaba y se descartaba): ahora entran las oportunidades que empiezan antes del fin del horizonte y las que no tienen fecha de inicio. Pantallas: `ResourceForecastPage` y `ResourceHeatmap` (`prefijo: 'mapa_'`) usan `SelectorDePeriodo` hacia delante sin «próximos 365 días» (pasaría de 52 semanas). `/resource-forecast/availability` ya tenía rango libre (`from_date`/`to_date`) y no se tocó; `ResourceSchedulerPage` es navegación de calendario y sigue con `weeks`.
3. **`/bi/data/timesheets`** (token BI, sin usuario): `desde`/`hasta`/`granularidad`/`tz`; las fechas sin zona se interpretan en la zona de la empresa del token (`Organization.timezone`); `date_from`/`date_to` (incluido) siguen valiendo. Con `granularidad` devuelve la serie agregada (`t`, `clave`, `hours`, `billable_hours`, `entries`) sin paginar; sin ella, las filas paginadas de siempre. El periodo se valida después del token (401 antes que 422). Además `_check_bi_token_auth` publica en la sesión la empresa del token: **antes la sesión de `/bi/data/*` iba sin contexto, el filtro automático se saltaba y devolvía datos de todas las empresas**. Un token sin empresa no ve filas de ninguna.
4. **Exportación BI a Excel/PowerPoint**: las cifras salen del periodo, por mes. Antes leía una instantánea `bi.etl.sync_data.internal.<org>` que ningún conector escribe y, sin ella, exportaba **seis meses de cifras de demostración**; el periodo solo cambiaba la etiqueta. Ahora: ingresos = `Invoice.total` por `issue_date` (sin borradores ni anuladas), tickets creados en el periodo, SLA por mes = (tickets − incumplidos)/tickets (mes sin tickets = sin dato, no 0 %; la media ignora esos meses), resolución media de los tickets del periodo ya resueltos, proyectos activos = los activos ahora.
5. **403 antes que 422** en ABAC (`/abac/admin/*`) y gobierno de IA (`/ai-governance/audit-log`, `/audit-log/stats`): el permiso es una dependencia (`_permiso_de_gobierno`) declarada antes del periodo. FastAPI resuelve las dependencias en el orden de la firma y los errores de validación de la query solo se devuelven al final, así que un usuario sin permiso recibe 403 aunque el periodo esté mal formado.

**No migrado, con motivo.** Ventanas de algoritmo (correlación de alertas `window_hours`), retención (`keep_days`, `clear-old`, `data_retention_days`), navegación de calendario (imputar por semana, calendario, ausencias por mes, carga de una semana, planificador visual de recursos), listados CRUD con filtro de fecha (gastos, partes, imputaciones, ausencias), el ejercicio contable del reconocimiento de ingresos, campos de factura (`period_from/to`), detección de anomalías y previsión (series mensuales fijas, horizonte de N puntos) y la agenda futura del chat (`/calendar/events`).

**Tests.** `tests/test_periodo_libre.py` (dependencia, alias, agrupación SQLite = Python, límites), `tests/test_periodo_{seguridad,service_desk,finanzas,tiempo}.py`, `tests/test_periodo_restos.py` (margen OLAP en el respaldo y en DuckDB, horizontes de previsión y demanda, BI timesheets con zona y empresa del token, cifras de la exportación BI, 403 antes que 422), `frontend/src/__tests__/SelectorDePeriodo.test.tsx`, `SelectorDeFecha.test.tsx`, `ResourceHeatmap.test.tsx` y `ResourceForecastPage.periodo.test.tsx`.

## Canales en tiempo real (17-11-2026)

Revisión de base de datos **179** (`alembic/versions/179_canales_tiempo_real.py`, sobre `178_externos_como_internos`, con downgrade). Uso en `docs/SERVICE_DESK.md` (misma sección); despliegue y permisos de la app de Slack en `docs/DESPLIEGUE.md` (B.1).

- **Slack, hilos ↔ ticket** (`canal_slack.py`): Events API en `POST /sd/channels/slack/events` (`leer_evento`: `url_verification` firmado con cualquier signing secret conocido; `event_callback` con el de la empresa del `team_id`; `procesar_evento` va por `encolar`, en el worker). El vínculo es una `ChannelConversation` `slack` con `external_id = <canal>:<ts raíz>` (`vincular_hilo`); nace con `/contecflow ticket` (el receptor deja `channel_id` en `db.info["slack_canal"]` y `crear` publica la tarjeta con el token del bot), con el aviso del ticket nuevo en `SD_SLACK_TICKET_CHANNEL` (`publicar_aviso_de_ticket`, evento `created` de la bandeja) o con un mensaje raíz en `SD_SLACK_INTAKE_CHANNELS`. Respuesta en el hilo → comentario público (`conversaciones.mensaje_del_cliente` con `autor_usuario`/`autor_nombre`; autor por correo con `users.info`: usuario, contacto del portal o «Cliente externo»), ficheros bajados de `files.slack.com` con el token. Sin bucles: `bot_id`, subtipos distintos de `file_share`/`thread_broadcast`, el usuario del bot (`authorizations`); y cada mensaje guarda su `ticket_comment_id`. Token: credencial cifrada `slack.bot_token` (sin respaldo global). API con `cliente_httpx` y `outbound_http_timeout`.
- **Salida por los canales** (`salida_por_canales.py`): `entregar` (texto de la bandeja), `entregar_adjunto` (documento del ticket a WhatsApp o al hilo) y `al_comentar` (respuesta pública de un agente en el ticket → cada conversación abierta de WhatsApp/Slack del ticket; la llama `ticket_event_processor._por_los_canales` al final del evento, sin lanzar). `delivery_status` en cada mensaje.
- **WhatsApp** (`canal_whatsapp.py`): medios entrantes (`_medio`: `GET /{media_id}` y descarga solo de hosts de Meta, con tope); salientes (`enviar_adjunto`: `POST /{phone_number_id}/media` + mensaje por id). Ventana de 24 h (`ventana_abierta`, `sd_channel_conversations.last_inbound_at`); fuera, plantilla (`whatsapp.template_name`/`template_language`, variables sin saltos de línea) o 409 antes de guardar. Todo con `cliente_httpx`.
- **Adjuntos de canal** (`adjuntos_de_canal.py`): tope `SD_CHANNEL_MAX_ATTACHMENT_MB`, `validate_upload` con el perfil nuevo `UploadProfile.CHANNEL` (`app/core/uploads.py`: sin SVG; con ogg/opus/aac/amr/3gp/mov), `scan_with_av` (infectado → `UPLOAD_BLOCKED` en auditoría) y documento del ticket (`Document` + `DocumentVersion`, dueño como en el correo entrante). `GET /sd/channels/conversations/{id}` trae `attachments` (documentos del ticket) y `POST /sd/channels/conversations/{id}/attachments` los envía (auditado `SEND channel_attachment`).
- **Tiempo real** (`canales_en_vivo.py`): empuja `livechat` al cliente (`client:<id>`) y `sd_channel` a los operadores con la bandeja abierta (`channel_watch`, registro por empresa en Redis o memoria, 90 s), siempre después de `commit`. Entrada: `ws.py` delega `channel_typing`/`channel_read` (operador, conversación de su empresa) y `livechat_typing`/`livechat_read` (cliente, conversación suya) en `mensaje_del_operador`/`mensaje_del_portal`. «Leído»: `client_read_at`/`agent_read_at`. Frontend: `usePortalEnVivo.ts` (socket del portal compartido; `PortalClientePage` lo usa), `enviarPorAvisosEnVivo` en `useAvisosEnVivo.ts`, `PortalChatEnVivo` y `BandejaDeCanales` sin sondeo mientras hay socket.
- **Asistente del portal con IA** (`asistente_del_portal_ia.py`): `call_ai` con el módulo `portal_assistant` (nuevo en `MODULOS_DE_IA`: ruta por función y tope de gasto), salida JSON con una herramienta de `POLITICAS_DEL_PORTAL` (nueva `portal_kb_search` → `/sd/kb/suggest`), validada en el servidor; las de escritura solo proponen (`PortalAssistantAction.engine`). Las de lectura se redactan con una segunda llamada SOLO con los datos. Idioma: el del portal (`language` en `POST /sd/portal-assistant/intent`, más `history`). Sin IA → `_interpretar` por palabras con `notice: ai_unavailable`. Auditoría `PORTAL_ASSISTANT` en cada acción, confirmación y descarte.
- **Ajustes** (grupo Service Desk): `SD_SLACK_TICKET_CHANNEL`, `SD_SLACK_INTAKE_CHANNELS`, `SD_CHANNEL_MAX_ATTACHMENT_MB`, `SD_PORTAL_ASSISTANT_AI`, `SD_PORTAL_ASSISTANT_MAX_TOKENS`.
- **Pruebas**: `tests/test_canales_tiempo_real_2026_11.py` (dobles de Slack, Meta, LLM y almacén), `tests/test_sd_mercado_canales_2026_11.py` (doble de `cliente_httpx` para WhatsApp), `frontend/src/pages/portal-client/__tests__/usePortalEnVivo.test.tsx`. Resultados: ver el informe de la entrega.

## Margen, versiones de avisos y catálogo, errores de validación (17-11-2026)

Revisión de base de datos **181** (`alembic/versions/181_versiones_avisos_y_catalogo.py`, sobre `180_turnos_y_ausencias_por_horas`, con downgrade).

- **Evolución del margen** (Rentabilidad, `/profitability`): sección «Evolución del margen» (`frontend/src/pages/profitability/EvolucionDelMargen.tsx`) con `SelectorDePeriodo` (día, semana o mes; prefijo `mev_` en la URL), gráfico de ingreso, coste, margen % y proyectos activos, y desglose del periodo por proyecto o por cliente; al pulsar una fila el gráfico se filtra a ese proyecto o cliente. API (solo admin y PM, como la rentabilidad): `GET /analytics/olap/margin-evolution` (ahora con `revenue`, `margin`, `margin_pct` (null sin ingreso) y `hours`, filtros `proyecto_id`/`cliente_id`; `months` sigue valiendo) y `GET /analytics/olap/margin-evolution/breakdown?por=proyecto|cliente&limit=`. Lo calcula `app/services/evolucion_del_margen.py` sobre la base transaccional con las reglas de la rentabilidad repartidas por fecha: ingreso por `profitability_service.partidas_de_ingreso` (tablas de tarifas, luego tarifa del proyecto, luego hitos facturados en `billed_at`); coste de personal con cambio de moneda (`coste_de_imputacion_en_moneda`), gastos y subcontrata (`costes_de_proyecto.partidas_externas`) y ALM por tramo. La suma de los tramos es la rentabilidad del periodo. No usa DuckDB: su esquema estrella no tiene ingreso (`query_engine.get_margin_evolution` sigue, sin ruta que la llame). Proyecto o cliente de otra empresa: 404 con código.
- **Versiones revisables de avisos y catálogo** (`app/services/traduccion/versiones_del_portal.py`, modelo `PortalContentTranslation`, tabla `portal_content_translations`): como las de la KB, para avisos (`announcement`: título y cuerpo) y nombre y descripción de categorías y servicios del catálogo (`catalog_category`, `catalog_service`). Nacen en revisión (`generar`, a los idiomas de `TRANSLATION_KB_LANGUAGES`), se corrigen (`editar`: vuelven a revisión y toman el original de ahora como base) y las publica o rechaza (con motivo) un revisor: administrador o miembro de la cola `SD_KB_REVIEWER_GROUP_ID` (la de la KB); generar, corregir y borrar, administrador o revisor. El portal (`GET /sd/announcements`, `GET /sd/catalog`) sirve la publicada en su idioma (`translation_reviewed: true`) y, si no la hay, la traducción automática en caché de siempre (`translated_from` + `original`: la marca «Traducido automáticamente»), en una sola llamada al proveedor para categorías y servicios. Desactualizada: `source_hash` (huella de los textos originales) distinta de la actual; la publicada se sigue sirviendo. Al guardar un cambio del original (`PATCH /sd/catalog/categories/{id}`, `PATCH /sd/catalog/services/{id}` y el nuevo `PATCH /sd/announcements/{id}`) la respuesta trae `translations_outdated` y, si hay alguna, se avisa a los revisores (campana) y se audita. API: `GET /translation/portal-content` (pantalla de revisión: cada aviso, categoría y servicio activos con sus versiones por estado y desactualizadas) y `GET|POST generate|PATCH|POST review|DELETE /translation/portal-content/{tipo}/{id}[/{idioma}]`. Auditoría `TRANSLATE`/`UPDATE`/`APPROVE`/`REJECT`/`DELETE` sobre `portal_content_translation`. Frontend: el panel de la KB pasa a ser genérico (`components/traduccion/VersionesPanel.tsx`, con un adaptador por uso; `VersionesKbPanel` es el de la KB) y `VersionesDeContenidoPanel` el de avisos y catálogo; botón «Idiomas» en cada categoría, servicio y aviso de Service Desk → Configuración; subpestaña «Traducciones del portal» (`RevisionDeContenidoDelPortal.tsx`) con lo pendiente primero. Los avisos se pueden editar.
- **Errores de validación con código** (`app/core/validacion.py`, manejador en `app/main.py`): un 422 de `RequestValidationError` sale como `{detail: "Revisa los datos: campo (tipo)…", code: "validacion", params: {errores: [{campo, tipo, origen, min?, max?, permitidos?}]}}`, con tipos normalizados (`obligatorio`, `formato`, `numero`, `entero`, `fecha`, `booleano`, `minimo`, `mayor_que`, `maximo`, `menor_que`, `longitud_minima`, `longitud_maxima`, `elementos_minimos`, `elementos_maximos`, `valor_no_permitido`, `campo_no_permitido`, `tipo_incorrecto`, `json_invalido`, `no_valido`). Ya no se devuelve el valor enviado (`input`), que podía ser una contraseña. `validacion` está en el catálogo de códigos (`err_srv.validacion` en los 8 idiomas del portal) y cada tipo en `validacion.<tipo>` (operador es/en/zh y portal 8). Frontend: `utils/erroresDeValidacion.ts`; `extractErr` resume el error ya traducido; hook del kit `useErroresDeCampo` (`recoger(e)` en `onError`, `de(campo)` en el `error` de `Input`/`Select`/`FormField`, `limpiar`). Formularios con error por campo: ticket del service desk, proyecto, cliente (alta y edición), usuario, tarea (alta), imputación, gasto, oportunidad, contrato, factura (alta), categoría, servicio y aviso del catálogo; en el portal, nuevo ticket, solicitud de cambio, perfil y cambio de contraseña (`PortalField` admite `error`).
- **Pruebas**: `tests/test_evolucion_del_margen.py`, `tests/test_versiones_avisos_y_catalogo.py`, `tests/test_validacion_con_codigo.py`, `frontend/src/__tests__/erroresDeValidacion.test.ts`.

## Restos antes de la prueba general (17-11-2026)

Revisión de base de datos **182** (`alembic/versions/182_comentarios_de_canal_y_festivos_por_empresa.py`, sobre `181_versiones_avisos_y_catalogo`, con downgrade).

- **Adjuntos desde la ficha del ticket**: `GET /sd/channels/tickets/{id}/conversations` (`conversaciones.del_ticket_para_adjuntos`: conversaciones abiertas de WhatsApp/Slack del ticket de la empresa y sus documentos; 404 con código si el ticket no es de la empresa). El envío es el de la bandeja (`POST /sd/channels/conversations/{id}/attachments`: ventana de 24 h, hilo de Slack, auditoría `SEND channel_attachment`). Frontend: `components/servicedesk/AdjuntosPorCanalDelTicket.tsx` en `TicketDetail` (solo si hay conversación abierta; `Ventana` se comparte con `BandejaDeCanales`).
- **Slack, ediciones y borrados** (`canal_slack.procesar_cambio`): `message_changed`/`message_deleted` de una respuesta de hilo que ya entró como comentario. Edición: `body` nuevo y `sd_ticket_comments.edited_at`; borrado: `retracted_at` y `body` vacío. El texto anterior queda en la auditoría (`UPDATE`/`RETRACT` sobre `ticket_comment`, `old_values`). Sin bucles: no pasa por los eventos del ticket (no sale a canales ni avisa) y se ignoran bots y mensajes que no entraron. La ficha y el portal enseñan «editado» y «Comentario retirado por su autor» (`edited_at`/`retracted_at` en `ticket_out`).
- **Errores del operador con código**: `codigos_de_error.MENSAJES_DEL_OPERADOR` (solo operador; `texto()` mira los dos catálogos, `TODOS`), con `err_srv.<código>` en `i18n/langs/{es,en,zh}.mjs`. `extractErr` los traduce (`utils/errorDelOperador.ts`), así que cualquier aviso de operador sale en su idioma sin cambiar la pantalla. Con código: ventana de WhatsApp (texto y adjuntos), Slack sin token, canal sin adjuntos, conversación sin ticket, adjunto no encontrado; jornadas, asignaciones, ficha laboral, ajustes de saldo y bolsa, ausencias por horas y saldo insuficiente, turnos, sedes de festivos, avisos. Sin código queda el 422 de `guardar_jornada` con detalle estructurado (`{"message", "errors"}`).
- **Error por campo**: `useErroresDeCampo` también en edición de tarea (`TaskDetailModal`), edición en línea de imputación, `PortalUsersTab` (alta, edición, contraseña) y el resto de formularios de alta/edición encontrados sin él (ausencias y su administración, externos, ALM, CMDB, riesgos, épicas, entregables, OKR, formación, cambios, KB, etc.).
- **Festivos de la semilla**: `_sembrar_festivos(db, org)` va después de la empresa y los crea con su `organization_id` (el horario efectivo solo cuenta los de la empresa). La 182 copia los festivos sin empresa a cada empresa (sin duplicar día y nombre) y borra los globales (`festivos_por_empresa`, idempotente).
- **Recuentos de arquitectura**: `RUTAS_ESPERADAS` 1165 (+1 `POST /sd/channels/conversations/{id}/attachments`), exención «sin sujeto autenticado» 53 (+1 `POST /sd/channels/slack/events`, firmado), README con las filas de `SD_PORTAL_ASSISTANT_AI`, `SD_PORTAL_ASSISTANT_MAX_TOKENS`, `SD_SLACK_TICKET_CHANNEL`, `SD_SLACK_INTAKE_CHANNELS` y `SD_CHANNEL_MAX_ATTACHMENT_MB`.
- **Pruebas**: `tests/test_restos_canales_2026_11.py`, `tests/test_errores_del_operador_turnos.py`, `tests/test_seed_fases.py` (festivos por empresa).

## 23. PRD MVP — Chat interno back office

> **Documento histórico: el MVP está implementado** (estado a 16-11-2026; uso y límites en el README, «Chat (Teams) — `/chat`»). Se conserva el PRD tal cual se escribió. Lo que difiere del texto de abajo:
> - **Stack decidido:** motor de mensajería propio en la API (`app/services/collaboration/`, unas 100 rutas bajo `/api/v1/collaboration/*`, WebSocket `/api/v1/collaboration/ws`), no Matrix ni un SaaS; medios con LiveKit (`LIVEKIT_*`); adjuntos en almacenamiento local o S3 (`COLLAB_STORAGE_BACKEND`), subidas reanudables tus, antivirus ClamAV opcional (`CLAMAV_ENABLED`).
> - **Modelo de datos:** tablas `collaboration_*` (no las `chat_*` del borrador).
> - **Hecho:** canales, mensajes directos y de grupo, hilos, reacciones, edición y borrado, adjuntos, presencia, búsqueda, avisos, llamadas de voz/vídeo, retención, bloqueo legal y auditoría.
> - **Límites medidos:** sin credenciales de LiveKit la llamada es solo una vista previa local; «grabar» no graba (no hay egress); el cifrado de extremo a extremo es opcional (`docs/COLLABORATION_E2E_ENCRYPTION_OPTIONAL.md`); con el bus `memory` y varios workers la entrega en tiempo real no está verificada.

### Objetivo
Canal de comunicación interno unificado para equipos de back office con mensajería en tiempo real, llamadas de voz/video y compartición de archivos, integrado con autenticación y permisos corporativos existentes.

### Alcance del MVP (in)
- Chat en canales públicos/privados.
- Mensajería directa 1:1.
- Edición y borrado de mensajes propios (ventana temporal configurable).
- Adjuntos (imágenes, PDF, Office) con vista previa básica.
- Llamadas de voz y videollamadas de grupo.
- Presencia (online/away/offline) y estados de lectura.
- Búsqueda por texto en mensajes y archivos compartidos.
- Notificaciones in-app y badge de no leídos.
- SSO corporativo + control de acceso por rol/organización.

### Fuera de alcance MVP (out)
- Grabación de llamadas con transcripción automática.
- Federación externa entre organizaciones.
- Bots avanzados y marketplace de apps.
- E2E encryption por defecto en todas las salas.
- eDiscovery legal avanzado.

### Perfiles y permisos (RBAC inicial)
- Admin sistema: configuración global, políticas de retención, auditoría.
- Manager back office: crea canales de equipo, modera miembros y permisos.
- Usuario interno: chat, llamadas, adjuntos en canales permitidos.

### Requisitos funcionales clave
- RF-01: envío/recepción de mensajes en < 500 ms en red corporativa normal.
- RF-02: entrega confiable con reintento y confirmación de estado.
- RF-03: subida de archivo hasta 100 MB por adjunto (configurable).
- RF-04: llamadas de hasta 25 participantes en MVP.
- RF-05: historial accesible por permisos del canal.
- RF-06: auditoría de acciones sensibles (borrado, cambios de permisos, expulsión).

### Requisitos no funcionales
- RNF-01: disponibilidad objetivo 99.9% mensual.
- RNF-02: cifrado TLS en tránsito y cifrado en reposo para adjuntos.
- RNF-03: trazabilidad con correlation id por evento.
- RNF-04: observabilidad (logs, métricas, alertas) desde día 1.
- RNF-05: cumplimiento de políticas de retención internas por canal.

### Arquitectura técnica recomendada
Patrón: experiencia integrada en Contecflow + motores especializados.

Componentes:
- Frontend SPA (módulo chat): canales, DM, hilos, llamadas, archivos.
- API Contecflow: permisos, metadata de canales, auditoría, políticas.
- Motor de mensajería real-time (recomendado Matrix/Synapse o equivalente).
- Motor de media WebRTC (recomendado LiveKit/Jitsi SFU).
- Almacenamiento de adjuntos (S3 compatible, URL firmada con expiración).
- Cola/event bus para eventos internos (notificaciones, auditoría, webhooks).

Flujo resumido:
1. Usuario autentica por SSO.
2. Entra a canal autorizado por RBAC/`organization_id`.
3. Mensajes vía WebSocket y persistencia en motor de chat.
4. Archivos vía upload firmado + escaneo antivirus + metadatos en DB.
5. Llamadas con sala WebRTC y TURN/STUN para redes restringidas.

### Modelo de datos mínimo
- `chat_channels`
- `chat_channel_members`
- `chat_messages`
- `chat_message_reads`
- `chat_attachments`
- `chat_calls`
- `chat_call_participants`
- `chat_audit_events`

### Seguridad y compliance
- Autenticación SSO/OIDC y sesiones con expiración.
- Aislamiento estricto por `organization_id`.
- Política DLP básica en adjuntos (MIME permitido + antivirus).
- URLs firmadas de descarga con TTL corto.
- Registro de auditoría para cambios de rol/permisos y moderación.

### Mockup funcional (desktop)
```text
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ [Contecflow Chat]  Buscar...                           [+]  [Llamada] [Video] [Perfil]   │
├──────────────────┬─────────────────────────────────────────────────┬────────────────────────┤
│ Canales          │ #operaciones                                    │ Detalle canal          │
│ - #general       │ [09:10] Marta: Cerramos reporte mensual hoy?   │ Miembros: 18           │
│ - #operaciones   │ [09:11] Oriol: Si, lo subo en 20 min           │ Archivos: 124          │
│ - #rrhh          │ [09:12] Ana: Adjunto informe.pdf               │ Enlaces fijados: 6     │
│                  │          [informe.pdf]                          │                        │
│ Mensajes directos│ ------------------------------------------------ │ Llamada activa         │
│ - Pau            │ Escribe un mensaje...              [Adjuntar]   │ [miniaturas x4]        │
│ - Ana            │                                                 │ [Silenciar][Compartir] │
└──────────────────┴─────────────────────────────────────────────────┴────────────────────────┘
```

### Plan de implementación por fases
- Fase 0 (1-2 semanas): discovery, UX, criterios de seguridad, PoC de stack.
- Fase 1 (3-4 semanas): chat canales + DM + presencia + notificaciones.
- Fase 2 (2-3 semanas): adjuntos seguros + preview + políticas básicas.
- Fase 3 (3-4 semanas): voz/video + TURN/STUN + controles de llamada.
- Fase 4 (2 semanas): hardening, observabilidad, piloto interno y rollout.

Estimación MVP: 8-12 semanas según nivel de integración y compliance.

### KPIs de éxito del MVP
- Adopción semanal (% usuarios activos de back office).
- Tiempo medio de respuesta en canal.
- Éxito de conexión en llamada (> 98%).
- Latencia p95 de envío de mensaje.
- Incidencias de seguridad/compliance (objetivo: 0 críticas).

### Riesgos técnicos y mitigación
- Red corporativa bloquea WebRTC: desplegar TURN propio y pruebas tempranas.
- Fuga de datos en adjuntos: antivirus + DLP + TTL corto en descargas.
- Sobrecarga del sistema de eventos: colas y límites por canal/usuario.
- Complejidad operativa: preferir motores maduros frente a desarrollo desde cero.

### Decisión arquitectónica pendiente
Stack final:
1. Opción A (self-hosted): Matrix + LiveKit + MinIO.
2. Opción B (SaaS): Stream/Sendbird + proveedor WebRTC gestionado.

Decidir en comité técnico con criterios de coste, soberanía de datos y esfuerzo de operación.
