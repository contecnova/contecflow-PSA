# Mi cuaderno (23-11-2026, migración 202)

Un OneNote dentro de la herramienta para cada persona con acceso a gestión
(internos y externos con sesión de operador). **No** es para los usuarios del
portal de clientes: el portal usa otra sesión y no tiene las capacidades
`cuaderno.*`.

- Página completa: **Mi trabajo › Mi cuaderno** (`/notebook`), con el árbol a la
  izquierda y el editor a la derecha.
- Panel rápido: icono de cuaderno en la barra superior (junto al chat y el
  calendario). Abre un panel lateral con las notas rápidas y las páginas
  recientes desde cualquier pantalla.
- Configuración: **Configuración › Personas › Mi cuaderno** (`/settings/cuaderno`).

## 1. Funciones

### Fase 1: núcleo

| Función | Cómo |
|---|---|
| Cuadernos → secciones → páginas y subpáginas | Las secciones son pestañas de color. Las subpáginas cuelgan de `parent_id`. |
| Orden libre | Se arrastran las páginas (sobre otra página o sobre una sección). Para teclado y lectores de pantalla, cada elemento tiene un menú con Subir, Bajar, Convertir en subpágina, Sacar de la subpágina y Mover a otro cuaderno. Backend: `POST /notebook/reorder`, `PATCH /notebook/pages/{id}`. |
| Fecha y búsqueda | Cada página muestra cuándo se creó y cuándo se guardó por última vez. El buscador del árbol busca en el título y en el texto (`GET /notebook/search`). |
| Editor de texto rico | TipTap 3 (ProseMirror): títulos, listas, tablas, resaltado, enlaces, casillas de tarea con fecha y aviso opcionales, y etiquetas tipo OneNote (Pendiente, Importante, Pregunta, Idea, Llamar a…, Crítico). Las etiquetas por defecto se configuran en Configuración y cada persona puede crear las suyas (`/notebook/tags`). |
| Guardado automático | Se guarda 1,2 s después de dejar de escribir y al salir de la página. El indicador muestra «Guardado · hora», «Guardando…», «Sin conexión: guardado en este equipo» o «No se pudo guardar». |
| Papelera | Borrar manda el elemento a la papelera (`deleted_at`); desde ahí se restaura o se borra del todo. Se purga sola pasados `trash_days`, salvo bloqueo legal. |

**Por qué TipTap.** Es ProseMirror: un esquema estricto, cuyo JSON el servidor
puede validar, sin HTML libre. Cada función es una extensión pequeña (tablas,
casillas, resaltado, menciones) y tiene colaboración Yjs oficial
(`@tiptap/extension-collaboration` sobre `@tiptap/y-tiptap`, una bifurcación
mantenida de y-prosemirror). `yjs` ya estaba instalado. Se carga en diferido:
solo al abrir la página o el panel. Paquetes: `@tiptap/*` 3.35.0, instalados con
el lockfile.

### Fase 2: conectado con la herramienta

- **Enlaces vivos.** `#` busca tareas, tickets, proyectos y clientes; `@` busca
  personas. Cada uno usa el MISMO alcance que el listado de su módulo
  (`cab_service.busqueda.consulta_de_*`). El chip muestra el estado actual
  (`POST /notebook/chips/resolve`, en lote y con caché de un minuto). Si quien
  lee no tiene permiso para ver el objeto, el chip sale «Sin acceso», sin título
  ni estado, y el servidor borra su etiqueta del JSON que entrega a los lectores
  que no son el dueño (`acciones.redactar`).
- **De nota a acción.** Se selecciona texto, o se pone el cursor en una casilla,
  y se pulsa ⚡. El texto pasa a tarea (en un proyecto visible), ticket,
  solicitud de demanda, idea de cartera o recordatorio de calendario. El vínculo
  queda en los dos sentidos: la descripción del objeto creado lleva el enlace
  `/notebook?page=<id>`, la nota inserta el chip y `notebook_links` guarda
  `relation=created`. Las notas que enlazan un objeto se consultan en
  `GET /notebook/backlinks`. Cada opción solo aparece para quien tiene la
  capacidad: `tareas.usar` o `tareas.crear`, `sd.trabajar` o `cartera.usar`.
- **Todas mis tareas y etiquetas.** Junta las casillas pendientes y las
  etiquetas de todos los cuadernos que la persona puede leer
  (`GET /notebook/items`). Está en la pestaña «Tareas y etiquetas» de Mi
  cuaderno, en la pestaña «Mi cuaderno» de la bandeja de entrada y en el bloque
  «Pendiente en mis notas» de Mi día. Marcar una casilla desde ahí la marca
  también en la página.
- **Avisos.** Una casilla con aviso (`remind`) manda una notificación a la
  campana de su dueño. Lo hace el trabajo `cuaderno-avisos` cada 5 minutos y
  avisa una sola vez por aviso.
- **Volcado de reuniones.** El detalle de una reunión tiene el botón «Enviar a mi
  cuaderno» (`POST /notebook/from-meeting/{id}`). Crea una página con fecha,
  asistentes, resumen, decisiones, preguntas abiertas y las acciones como
  casillas, con su responsable como `@` y las tareas o tickets ya creados como
  `#`. Solo funciona con reuniones que la persona puede ver.
- **Búsqueda global y ⌘K.** Las páginas aparecen en el grupo «Notas» de
  `/global-search`, pero solo las del dueño o las compartidas con quien busca.

### Fase 3: colaboración

- **Compartir** un cuaderno entero o una sección con una persona, un equipo
  (`users.team`) o un departamento (`users.department`), en lectura o edición.
  Solo comparte el dueño. Las notas rápidas no se comparten. Configuración
  decide a qué tipos de destinatario se puede compartir. La persona recibe un
  aviso.
- **Edición simultánea** (Yjs) por `/ws/notebook/{page_id}`. Es la misma
  infraestructura que `/ws/doc`: salas locales más Redis, ticket de un solo uso
  y tope de 2 MB por mensaje. Quien solo lee recibe los cambios, pero los suyos
  se descartan. El estado se guarda en `document_collab_snapshots`
  (`document_id` = página, `metadata_json` `{"kind":"notebook_page"}`) con cada
  guardado, con tope de tamaño y de historial (`CUADERNO_COLLAB_HISTORY_MAX`).
- **Adjuntos e imágenes pegadas o soltadas.** Pasan por el validador central de
  subidas (perfil ATTACHMENT) y se guardan en el almacén común. Se sirven por
  `/notebook/attachments/{id}/file` solo a quien puede leer la página, con
  `nosniff` y CSP `sandbox`. Lo que no es una imagen rasterizada se descarga.
- **Dibujo** a mano alzada o con lápiz (Pointer Events, con presión). El
  navegador manda los trazos en JSON y el servidor genera el SVG: no puede
  llevar texto libre ni scripts. Los trazos se guardan para poder editar el
  dibujo después.

### Fase 4: extras

- **Voz.** Graba en el navegador y transcribe con la transcripción de las
  reuniones (`reuniones.transcripcion.transcribir`), que aplica los
  proveedores permitidos, el tope de gasto y el contrato del STT externo. El
  audio no se guarda salvo que se pida (`keep_audio`).
- **IA opcional**: resumir, extraer tareas y ordenar ideas
  (`POST /notebook/pages/{id}/ai`). Pasa por `call_ai_unified`, que aplica el
  proveedor y la ruta de la empresa, los guardarraíles, el registro y el tope.
  Antes comprueba el interruptor y el tope diario del módulo `notebook` en
  Gobierno de IA y `ai_enabled` en la configuración. Solo se manda el texto de
  esa página, y la respuesta no se guarda sola: la persona decide si la inserta.
- **Plantillas.** Hay cuatro de fábrica (acta de reunión, seguimiento de
  cliente, 1:1, lluvia de ideas) en es/en/zh, más las de la empresa. Se
  gestionan en Configuración y viven en `notebook_templates`. Si se edita una de
  fábrica, la editada manda sobre la del código; si se borra, vuelve la de
  fábrica.
- **Sin conexión.** IndexedDB guarda una copia de las últimas páginas abiertas y
  una cola de guardados pendientes. Cada persona y empresa tiene **su propia**
  base (`contecflow_cuaderno_<empresa>_<usuario>`), así que en el mismo
  navegador nadie lee ni sincroniza lo de otro. Al volver la red se manda lo
  pendiente con su `base_version`. Si la página cambió mientras tanto (409), lo
  escrito sin red se guarda como página nueva «(copia sin conexión)»: no se
  pierde nada ni se pisa lo de otra persona.

## 2. Permisos y privacidad

**Privado por defecto.** Un cuaderno solo lo ve su dueño. Se ve además lo que
se comparte expresamente. **Nadie más**: ni dirección, ni el superadministrador,
ni nadie con otra capacidad. Lo que no se puede ver responde **404**, para no
revelar que existe (`app/services/cuaderno/acceso.py`). La papelera solo la ve
su dueño. ABAC: `/api/v1/notebook` está exento (`abac_registry`) a propósito,
para que una política de empresa no pueda abrir notas ajenas.

| Capacidad | Roles | Qué abre |
|---|---|---|
| `cuaderno.usar` | admin, pm, team_lead, hr, employee, subcontractor | Sus cuadernos, notas rápidas, lo compartido con la persona, `/notebook`, panel rápido, bandeja y Mi día |
| `cuaderno.config` | admin | Configuración › Mi cuaderno |
| `cuaderno.acceso_excepcional` | admin | Descargar los cuadernos de una persona con un motivo verificable (ver GRC) |

Matriz por rol del contenido compartido:

| | Dueño | Compartido en edición | Compartido en lectura | Cualquier otro (también admin y superadmin) |
|---|---|---|---|---|
| Ver y buscar | sí | sí | sí | no (404) |
| Escribir, adjuntar, dibujar, voz, nota→acción | sí | sí | no (403) | no (404) |
| Crear secciones (cuaderno compartido entero) | sí | sí | no | no |
| Compartir, cambiar permisos, renombrar o borrar el cuaderno | sí | no | no | no |
| Exportar | sí | sí | sí | no |
| Papelera | sí | no | no | no |

Aislamiento por empresa: las nueve tablas llevan `organization_id`
(TenantSession y RLS), y todas las comprobaciones exigen además la empresa de
quien pregunta. No se puede compartir con alguien de otra empresa.

**Agentes de código (MCP, 23-11-2026, `docs/integraciones/MCP.md`).** El dueño
puede compartir un cuaderno (o una sección) con **sus propios** agentes de
código: *Compartir → «Compartir con mis agentes de código (MCP)»*. Es una fila de
`notebook_shares` con `target_type = agents` y `target_id` = el dueño, siempre
en lectura, sin aviso y auditada (`SHARE`/`UNSHARE`); no da acceso a ninguna
otra persona (`acceso.condicion_de_destinatario` no la mira). Solo se puede si la
empresa tiene encendido `MCP_NOTEBOOK_ENABLED` (si no, 403 `mcp_cuaderno_apagado`).
Las herramientas `search_notebook` y `get_notebook_page` leen solo páginas vivas
de cuadernos propios compartidos así, y cada lectura queda en `audit_log`
(`MCP_TOOL_READ`, canal `mcp`).

## 3. GRC

- **Auditoría** (`audit_logs`): crear cuaderno, sección y página; mandar a la
  papelera, restaurar y purgar; mover entre cuadernos; compartir, cambiar
  permiso y dejar de compartir (`SHARE`, `UPDATE`, `UNSHARE`); adjuntos y
  dibujos; transcripciones; nota→acción (`notebook_action_<tipo>`);
  exportaciones (`EXPORT`); volcado de reuniones; configuración y plantillas
  (antes y después); baja (`NOTEBOOK_OFFBOARDING`); purga de la papelera
  (`RETENTION_PURGE`); acceso excepcional (`NOTEBOOK_EXCEPTIONAL_ACCESS`). El
  texto de las notas **nunca** se escribe en la auditoría.
- **Acceso excepcional** (`POST /notebook/admin/exceptional-access/{user_id}`).
  Exige la capacidad, una justificación de al menos 10 caracteres y uno de estos
  motivos: un **bloqueo legal activo** que identifique a la persona (su id,
  correo o usuario; entidad `*`, `notebooks` o `notebook_pages`) o una
  **solicitud RGPD** suya en curso (`pending` o `processing`). Sin motivo
  responde 403. Entrega una exportación en Markdown o PDF y queda auditado con
  el motivo, la justificación, la IP y el número de páginas.
- **Exportación** de página, sección o cuaderno a **Markdown** y **PDF**
  (DejaVu, o STSong para chino). Sirve también para la portabilidad.
- **RGPD.** La copia de la persona (art. 15 y 20,
  `cab_service/gdpr._gdpr_portability_export`) incluye sus cuadernos, también
  los de la papelera, con cada página en Markdown y sus etiquetas. La supresión
  (`supresion_service.suprimir_persona`) borra sus cuadernos enteros (páginas,
  adjuntos, dibujos, audios e instantáneas), sus etiquetas y lo compartido con
  ella, y deja sin autor lo que escribió en cuadernos ajenos. Bajo bloqueo
  legal no se toca nada (409).
- **Baja de una persona** (`app/db/cuaderno_baja.py`, un `before_flush` que
  salta al desactivarla venga de donde venga). La política se elige en
  Configuración:
  - `transfer` (por defecto): los cuadernos pasan a su responsable
    (`manager_id`) con la marca «transferido de». Si no tiene responsable, se
    conservan y queda anotado en la auditoría.
  - `trash`: van a la papelera.
  - `keep`: se conservan.

  Lo compartido con la persona de baja se quita siempre.
- **Retención y bloqueo legal.** Tipos nuevos en `bloqueo_legal.TIPOS`:

  | Tipo | Qué alcanza | Desde |
  |---|---|---|
  | `notebooks` | Cuadernos de la papelera | Que se tiraron |
  | `notebook_pages` | Páginas de la papelera | Que se tiraron |
  | `notebook_attachments` | Adjuntos de páginas en la papelera | Su alta |

  Se puede bloquear por `owner_id` (persona), cuaderno, sección o página. Un
  bloqueo impide borrar venga de donde venga: papelera, purga diaria, supresión
  RGPD o retención.
- **Ficheros**: al borrar adjuntos o páginas por el ORM, sus ficheros del
  almacén y sus instantáneas Yjs se borran **después del commit**
  (`models/cuaderno._tras_borrar`). Si la transacción se deshace, no se borra
  nada.
- **Subidas**: pasan por el validador central (`app/core/uploads.py`). El SVG de
  los dibujos lo genera el servidor y la voz pasa por `validate_audio_upload`.
- **Contenido**: el servidor valida el JSON del editor (`contenido.validar`):
  solo admite tipos de nodo y marcas conocidos, limita la profundidad y el
  tamaño (`CUADERNO_PAGE_MAX_BYTES`), solo acepta enlaces http, https, mailto o
  rutas propias, y solo imágenes que sean adjuntos del cuaderno.
- **IA**: pasa por el proveedor y la gobernanza de la empresa (módulo
  `notebook`; registro de acciones y tope diario).

## 4. Modelo (migración `202_cuaderno`)

| Tabla | Qué guarda |
|---|---|
| `notebooks` | Cuadernos (dueño, color, orden, `is_quick` = notas rápidas, transferencia, papelera) |
| `notebook_sections` | Secciones (pestañas de color) |
| `notebook_pages` | Páginas y subpáginas: `content` (JSON de ProseMirror), `content_text`, `version`, plantilla y papelera |
| `notebook_shares` | Comparticiones (cuaderno o sección; persona, equipo o departamento; lectura o edición) |
| `notebook_items` | Índice de casillas (hecha, fecha, aviso) y etiquetas de cada página |
| `notebook_links` | Vínculos nota ↔ objeto (`mention` o `created`) |
| `notebook_tags` | Etiquetas propias de cada persona |
| `notebook_attachments` | Adjuntos, imágenes, dibujos (trazos en `meta`) y audios |
| `notebook_templates` | Plantillas de la empresa |

El dueño (`owner_id`) se repite en cada nivel para poder bloquear, exportar y
suprimir por persona. La configuración de la empresa vive en `app_settings`,
clave `cuaderno.config`: `tags`, `offboarding`, `trash_days`, `ai_enabled`,
`voice_enabled` y `sharing`.

Ajustes de la instalación (`Settings`, `.env.example`, docs/REFERENCIA_DE_AJUSTES.md):
`CUADERNO_PAGE_MAX_BYTES` (2 MB), `CUADERNO_COLLAB_HISTORY_MAX` (20) y
`CUADERNO_VOICE_MAX_BYTES` (25 MB).

Trabajos de fondo (Celery beat, y APScheduler cuando no hay Celery):
`cuaderno-avisos` (cada 5 minutos) y `cuaderno-papelera` (diario a las 03:55).

Errores con código: `scripts/codemods/errores_con_codigo/cuaderno.json`
(`cuaderno_*`).

## 5. Ficheros

- Backend:
  - `app/models/cuaderno.py`
  - `app/db/cuaderno_baja.py`
  - `app/services/cuaderno/*`
  - `app/api/v1/endpoints/cuaderno.py` (`/notebook`)
  - `app/api/v1/endpoints/ws.py` (`/ws/notebook/{id}`)
- Frontend:
  - `frontend/src/pages/CuadernoPage.tsx`
  - `frontend/src/components/cuaderno/*`: editor, extensiones, árbol, panel rápido, tareas, configuración, cola sin conexión y colaboración
  - `frontend/src/services/api/cuaderno.ts`
- Pruebas: `tests/test_cuaderno.py`.
