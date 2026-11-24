# BPM — Procesos de negocio (`/bpm`)

Guía para quien usa los procesos (diseña, inicia, completa tareas) y para quien
los administra (permisos, ajustes, auditoría, RGPD). Estado a 23-11-2026
(migración `204_bpm`). Sustituye a la sección «Revisión BPM (16-11-2026)» de
`DOCS.md` como referencia; aquella queda como historia.

## 1. Qué es

Un proceso es un diagrama **BPMN 2.0** (el estándar de Camunda, Bizagi o
Signavio) que la aplicación **ejecuta**: cada vez que se inicia nace una
*instancia*, una ficha que recorre el diagrama. Donde hace falta una persona
(una tarea, una decisión, una aprobación) la instancia espera en la **bandeja**
de quien le toca; lo automático (crear un ticket, pedir una aprobación, evaluar
políticas, avisar) lo hace el motor solo; los temporizadores los despierta el
worker cada minuto.

Piezas:

| Pieza | Dónde |
|---|---|
| Catálogo, editor, versiones, variables, prueba | `/bpm` → pestaña «Catálogo» (`pages/BPMPage.tsx`, `pages/bpm/*`) |
| Bandeja, instancias, métricas | `/bpm` → pestaña «Ejecución» (`pages/bpm/BpmRunPanel.tsx`); la bandeja también en `/inbox` → «Procesos» |
| Motor | `app/services/bpmn_engine.py` |
| Acciones automáticas | `app/services/bpmn_acciones.py` |
| Métricas y RGPD | `app/services/bpmn_gobierno.py` |
| Registro de procesos y versiones | `app/services/bpmn_process_service.py` |
| API | `/api/v1/bpmn-processes`, `/api/v1/bpmn-instances` |
| Worker | `app.worker.bpmn_vencer_temporizadores` (cada minuto) |
| Modelos | `app/models/bpmn_process.py` (4 tablas) |

## 2. Modelar

Se modela en el editor gráfico (bpmn-js) o se **importa** un `.bpmn` de otra
herramienta («Importar BPMN»). En edición, el **panel de propiedades** (debajo
del lienzo) muestra lo que el motor ejecuta del elemento seleccionado.

### Elementos que se ejecutan

| Elemento | Qué hace |
|---|---|
| Inicio simple | Arranca la instancia. Un inicio de mensaje o temporizador se acepta, con aviso, como inicio manual o por API. |
| Tarea de usuario / tarea / tarea manual | Espera en la bandeja de quien le toca (ver *Asignación*). |
| Tarea de servicio, de envío, de regla de negocio, de script | Con **acción** se ejecuta sola (sección 5). Sin acción, la confirma una persona en la bandeja. **Nunca se ejecuta código** escrito en el diagrama. |
| Tarea de recepción, evento intermedio de mensaje | Espera un mensaje con su nombre. |
| Evento intermedio de temporizador | Espera una duración (`PT2H`, `P1D`) o hasta una fecha ISO. |
| Compuerta exclusiva | La primera salida cuya condición se cumple; si no, la de por defecto. **Sin ninguna condición** es una decisión manual: alguien elige la salida en la bandeja. |
| Compuerta inclusiva | Reparte por **todas** las salidas cuya condición se cumple (o la de por defecto). Sin condiciones, decisión manual de una o varias salidas. Como unión, espera mientras quede alguna ficha que aún pueda llegar. |
| Compuerta paralela | Reparte por todas; como unión espera una ficha **por cada flujo de entrada**. |
| Subproceso | Ejecuta su interior (un único inicio simple) y sigue cuando no le queda nada pendiente dentro. |
| Llamada a proceso (`callActivity`) | Arranca la versión publicada de otro proceso de la empresa (por su clave) y sigue cuando termina, con sus variables. |
| Evento de borde | Temporizador (interrumpe o no: escalados), mensaje y error, sobre tareas, subprocesos y llamadas. |
| Fin | Normal; de **terminación** (corta su ámbito: el subproceso o la instancia); de **error** (lo captura el borde de error más cercano; si nadie, la instancia falla con el código). |
| Evento intermedio de lanzamiento sin definición | Pasa (hito). |

### Lo que no se ejecuta (y por eso no se publica)

Compensación, señales, escalados BPMN, eventos condicionales y de enlace,
compuertas complejas y por eventos, subprocesos de evento, transacciones,
actividades múltiples o en bucle, temporizadores cíclicos y varias piscinas con
inicio. Un diagrama que los usa se puede **guardar** (como documentación), pero
no **publicar** ni iniciar: la validación los lista con su motivo.

### Condiciones

`variable operador valor`, con `==`, `!=`, `>`, `<`, `>=`, `<=`, unidas por
`and`/`or` (o `&&`/`||`), `${…}` opcional. Ejemplos: `importe > 1000`,
`aprobado == true and pais == 'ES'`. Es una comparación, no código: lo que no
se puede leer se rechaza al validar.

### Asignación de tareas

En el panel de propiedades de una tarea (atributos `contecflow:*`; al importar
se aceptan también los de Camunda, `camunda:assignee`…):

- **Asignar a**: correo o id de una persona, `${initiator}` (quien inició) o
  `${variable}` (una variable con la persona). Solo esa persona (o un admin) la
  completa.
- **Grupos candidatos**: separados por comas; cada uno es un rol (`pm`, `hr`,
  `team_lead`, `employee`, `admin` o su nombre en pantalla), un **grupo de
  aprobación** o una **cola de agentes** del service desk, por su nombre (o
  `approval:<id>`, `team:<id>`).
- **Personas candidatas**: correos o ids.
- **Calle (lane)**: si su nombre es un rol o un grupo, también restringe.
- Sin nada de lo anterior, cualquiera de la empresa con acceso a BPM.

Quien gestiona (`bpm.gestionar`) puede **reasignar** o liberar una tarea desde
el detalle de la instancia. Al asignar una tarea a una persona se le avisa en
la campana.

### Plazo (SLA) de tareas

**Plazo** (`dueIn`, duración ISO: `PT4H`, `P2D`) o `dueDate` (fecha o
`${variable}`). Vencido, la tarea se marca «fuera de plazo» en la bandeja, se
avisa a la persona asignada y a quien inició, y queda en la auditoría
(`ESCALATE`), una vez. Para **cambiar el camino** al vencer, un borde de
temporizador (interrumpe: la tarea se cancela y sigue por el borde; no
interrumpe: abre un camino paralelo).

### Formularios

**Formulario** de una tarea: lista JSON de campos `name`, `label`, `type`
(`string`, `text`, `number`, `integer`, `boolean`, `date`, `enum` con
`options`, `user`), `required`, `personal`. La bandeja pinta el control de
cada tipo; el motor valida tipos y obligatorios y **no acepta datos que no son
del formulario**. Sin formulario, la bandeja ofrece variables libres
(`nombre=valor` por línea).

> La aplicación no tiene un catálogo reutilizable de formularios dinámicos (los
> «formularios dinámicos» del service desk son reglas de campos de tickets): por
> eso el formulario vive en la tarea.

### Aprobaciones

Una tarea con **«Es una aprobación»** se completa con *Aprobar* / *Rechazar*
(deja `aprobado = true/false`) y está sujeta a la segregación de funciones. Para
usar el **motor de aprobaciones** (grupos, quórum, niveles, escalados, correo),
una tarea de servicio con la acción `approval` (sección 5).

### Variables

«Variables» en el detalle del proceso declara las variables con su **tipo**,
si son **obligatorias** y si son **dato personal**. El motor convierte y valida
el tipo al iniciar, al completar y al recibir mensajes (`"3"` → `3` en un
entero; `"tres"` es un 422). Las no declaradas se aceptan tal cual. Las marcadas
como dato personal entran en la copia y la supresión RGPD.

## 3. Validar, probar y publicar

- **Guardar** crea una versión nueva (borrador) y dice si se puede ejecutar.
  El XML se parsea sin DTD, sin entidades y sin referencias externas
  (`defusedxml`, `forbid_dtd=True`): no hay XXE ni bombas de expansión; un XML
  roto o que no es BPMN 2.0 no se guarda (422). Tamaño máximo
  `BPMN_MAX_XML_BYTES`.
- **Validación**: *problemas* (impiden publicar) y *avisos* (no impiden:
  elementos inalcanzables, salidas sin condición que nunca se toman, inicio con
  definición).
- **Probar**: recorre la última versión en memoria, **sin escribir nada**, con
  las variables que se le den: las tareas se dan por hechas, temporizadores y
  mensajes llegan al momento, las acciones no se ejecutan (se listan). Dice por
  dónde pasa, si llega al final y **dónde se queda colgado** (por ejemplo, una
  unión paralela tras una compuerta exclusiva). Lo marca sobre el diagrama.
- **Versiones**: ciclo **borrador → publicada → retirada**.
  - Publicar exige un diagrama ejecutable; queda una sola publicada.
  - Las instancias nuevas usan la publicada. Mientras un proceso no ha
    publicado ni retirado nada, se inicia con la última guardada (modo
    borrador, para probar).
  - **Retirar** (con confirmación) impide instancias nuevas de esa versión; si
    se retiran todas, el proceso no arranca hasta publicar otra (409).
  - **Las instancias en curso siguen siempre en su versión.**
- **Archivar** el proceso impide instancias nuevas; **eliminar** (solo los
  propios, con confirmación) lo desactiva y cancela sus instancias.

## 4. Ejecutar y seguir

- **Iniciar** (`bpm.gestionar`): desde el detalle del proceso o por API
  (`POST /bpmn-processes/{id}/instances` con `variables` y `business_key`).
  La **clave de negocio** (p. ej. el número de pedido) sirve para buscar la
  instancia y para entregarle mensajes.
- **Bandeja** (pestaña «Ejecución» y `/inbox` → «Procesos»): las tareas y
  decisiones que el usuario puede completar, con proceso, clave de negocio, a
  quién están asignadas y su plazo; buscador.
- **Instancias**: lista con buscador (proceso, clave, id) y filtro por estado
  (`running`, `suspended`, `completed`, `cancelled`, `failed`). El detalle
  muestra el **diagrama de su versión** con lo hecho, lo pendiente y los
  incidentes, el historial (cada paso, quién lo hizo y cuándo) y las
  instancias llamadas. Acciones (con `bpm.gestionar`, las destructivas con
  confirmación):
  - **Suspender / reanudar**: suspendida, nadie completa sus pasos y sus
    temporizadores esperan; al reanudar, lo vencido salta en la siguiente
    pasada.
  - **Migrar** a otra versión: solo si cada paso pendiente existe igual
    (mismo id, tipo y ámbito) en la versión destino; si no, 409 con los pasos.
  - **Cancelar**: cancela sus pasos, cierra sus aprobaciones abiertas y
    cancela sus instancias llamadas.
  - **Reasignar** una tarea y **reintentar** un incidente.
- **Mensajes**: `POST /bpmn-instances/{id}/messages` o
  `POST /bpmn-instances/messages` (por clave de negocio) con `message` y
  `variables`. 404 si nadie lo espera.
- **Errores de negocio**: quien completa una tarea con borde de error puede
  «terminar con un error» (`error_code`); la ficha sale por el borde.

## 5. Tareas automáticas

Una tarea de servicio con **acción** se ejecuta sola en una cola: al iniciar o
completar se ejecutan las que tocan y el worker recoge las que quedan. Cada
acción corre en su propia transacción con la identidad y las capacidades de
**quien inició la instancia**.

| Acción | Configuración (JSON, `${variable}` se sustituye) | Deja |
|---|---|---|
| `set` | `{"variables": {"estado": "alta de ${nombre}"}}` | esas variables |
| `notify` | `{"to": "initiator" \| "${var}" \| correo, "message": "…"}` | — (aviso en la campana) |
| `ticket` | `{"title", "description"?, "project_id"?}` — exige `sd.trabajar` | `ticket_id`, `ticket_number` |
| `change` | `{"title", "project_id", "description"?, "justification"?}` — exige `cambios.responsables` | `change_request_id`, `change_request_code` (borrador) |
| `demand` | `{"title", "description"?, "type_key"?}` | `demand_id`, `demand_code` (borrador) |
| `approval` | `{"summary"?}`; `resultVariable` en la tarea | `aprobado` (o la indicada), `approval_status` |
| `policy` | `{"domain": "<dominio>", "resultVariable"?}` | `policy_decision` (`block`, `review`, `auto_approve`, `allow`) |

- **Aprobación**: abre una solicitud de tipo `bpmn_step` en el motor de
  aprobaciones, con las variables como contexto de sus reglas (ramas,
  auto-aprobación). Hace falta un flujo para `bpmn_step` en Aprobaciones; sin
  él, la tarea pasa a la bandeja de BPM como aprobación humana. La decisión
  final (bandeja de aprobaciones o correo) continúa la instancia.
- **Fallos**: se reintenta (`retries` en la tarea o `BPMN_SERVICE_RETRIES`,
  esperando 1, 2, 4… minutos). Agotados: si la tarea tiene un borde de error sin
  código o con `action_failed`, la ficha sale por él; si no, el paso queda como
  **incidente** (la instancia sigue en curso, sale en métricas) y se reintenta a
  mano.
- Sin acción, una tarea de servicio **espera confirmación humana** (la marca
  `automatic: false` de la auditoría del 22-11-2026): así los catálogos
  sembrados, cuyas tareas de servicio no tienen acción, no fingen
  automatización.

## 6. Métricas

Pestaña «Ejecución» → «Métricas» (`GET /bpmn-instances/metrics`, últimos 30
días, por proceso opcional): instancias iniciadas por estado, **duración**
(media, p50, p90), **cuellos de botella** (pasos humanos, de aprobación, de
mensaje o temporizador con más espera media y su p90), **instancias atascadas**
(en curso con un incidente, una tarea fuera de plazo o un paso pendiente desde
hace más de `BPMN_STUCK_HOURS`) y **tareas fuera de plazo**.

## 7. Permisos y aislamiento

| Capacidad | Quién (de serie) | Qué |
|---|---|---|
| `bpm.usar` | personal interno | ver procesos, versiones y validación; probar; bandeja; completar sus pasos; ver instancias y métricas |
| `bpm.gestionar` | dirección y PM | crear, editar, importar, versionar, publicar, retirar, archivar, eliminar, variables; iniciar; cancelar, suspender, reanudar, migrar, reasignar, reintentar; mensajes por API |
| `bpm.editar` | dirección y PM | la pantalla muestra las acciones de gestión (misma población que `bpm.gestionar`) |
| `procesos.bandeja` | personal interno | pestaña «Procesos» de `/inbox` |

Completar un paso exige además ser su persona asignada o candidata (rol, grupo,
cola o persona); el admin puede siempre, salvo la segregación de funciones.
Portal de clientes y subcontratistas: 403. Todo se acota por empresa (filtro de
tenant de la sesión y filtro explícito en el motor); una llamada a proceso solo
encuentra procesos de la misma empresa.

## 8. GRC

- **Auditoría** (`audit_log`): procesos — `CREATE`, `UPDATE`, `DELETE`,
  versión guardada, `PUBLISH`, `RETIRE`, siembra; instancias — `CREATE`
  (iniciar), `COMPLETE`, `CANCEL`, `SUSPEND`, `RESUME`, `MIGRATE`, `REASSIGN`,
  `RETRY`, `MESSAGE`, `ESCALATE`, `INCIDENT`, `AUTOMATIC_STEP`,
  `APPROVE`/`REJECT` (desde el motor de aprobaciones) y `SOD_BLOCKED`.
  El historial de pasos de cada instancia es además su traza.
- **Retención y bloqueo legal**: tipo `bpmn_instances` en Configuración →
  Retención: instancias **terminadas**, desde que terminan, con su historial en
  cascada. Se bloquean por `id`, `process_id`, `started_by_user_id` o
  `business_key`; una instancia bloqueada no se borra (ni por retención ni a
  mano) ni se tacha en una supresión RGPD. Las en curso nunca se retienen.
- **RGPD**: la copia de datos de una persona (acceso y portabilidad) incluye
  las instancias que inició (con sus variables) y los pasos que completó (con lo
  que aportó). La supresión tacha (`[ERASED]`) las variables marcadas como dato
  personal de lo que inició y, en cualquier instancia, los valores que son su
  correo, nombre, usuario o id; quién inició o completó queda en NULL al borrar
  la persona.
- **Segregación de funciones**: con `BPMN_SEGREGACION_DE_FUNCIONES` activo,
  quien creó o publicó la versión que corre no completa decisiones, tareas de
  aprobación ni aprobaciones `bpmn_step` en sus instancias (403, auditado). El
  admin no se la salta.

## 9. Ajustes (Configuración → Automatizaciones)

| Clave | Por defecto | Qué |
|---|---|---|
| `BPMN_MAX_AUTOMATIC_STEPS` | 500 | pasos automáticos seguidos antes de dar la instancia por bucle (falla) |
| `BPMN_MAX_XML_BYTES` | 2 000 000 | tamaño máximo de un diagrama (413) |
| `BPMN_MAX_VARIABLES_BYTES` | 65 536 | tamaño máximo de las variables (413) |
| `BPMN_SERVICE_RETRIES` | 3 | reintentos de una acción automática antes del incidente |
| `BPMN_STUCK_HOURS` | 72 | horas de un paso pendiente para contar la instancia como atascada |
| `BPMN_SEGREGACION_DE_FUNCIONES` | no | quien diseña o publica no aprueba |

## 10. Límites y lo que no hace

- No ejecuta código del diagrama (scripts, expresiones JUEL/FEEL): las
  condiciones son comparaciones y las acciones, una lista cerrada.
- No hay eventos de inicio programados (un temporizador de inicio no arranca
  solo), ni señales, compensación, escalados BPMN, actividades múltiples o
  bucles estándar, temporizadores cíclicos, subprocesos de evento ni varias
  piscinas colaborando.
- La llamada a proceso pasa **todas** las variables a la hija y recoge todas al
  volver (sin mapeo de entrada y salida).
- Suspender una instancia no suspende sus instancias llamadas.
- La migración de versión exige elementos con el mismo id; no reubica fichas.
- Las métricas miran 30 días (hasta 365 por API) y hasta 5 000 filas por
  consulta.
- El catálogo de procesos del sistema es documentación de cómo funciona la
  aplicación: iniciarlo crea su registro con el diagrama visto, pero sus tareas
  de servicio no tienen acción y las confirma una persona.
- 24-11-2026: el catálogo incluye **Conversación del portal (chat y llamadas)**
  (`portal_conversation`, service desk; 56 procesos sembrados, 40 lineales):
  mensaje del cliente → validar adjuntos (contenido por bytes, antivirus/DLP,
  tipos y tamaño por empresa) → política GRC y aprobación → respuesta del
  operador → **el operador** inicia llamada o videollamada → el cliente acepta o
  rechaza (nunca inicia: el servidor responde 403 `portal_llamada_solo_operador`)
  → llamada sin grabación y cierre. Documenta el flujo real de
  [docs/portal/CHAT_DEL_PORTAL.md](portal/CHAT_DEL_PORTAL.md); se resiembra con
  `seed_catalogue(force=True)` (los procesos personalizados no se tocan). Cubre
  las conversaciones formales y la pestaña «Chat» del portal (chat de colaboración).
- 24-11-2026 (migración 208): **Intake Multi-Canal** (`multichannel_intake`) gana el paso «Identificar
  empresa destinataria (sin ella, se ignora)»: un correo o SMS que no es de ninguna empresa (con varias) no
  abre ticket ([docs/seguridad/empresa_obligatoria.md](seguridad/empresa_obligatoria.md) §6). Se resiembra con
  `seed_catalogue(force=True)`.

## 11. Pruebas

`tests/test_bpm_profesional_2026_11_23.py` (compuertas inclusivas y
paralelas, bordes y plazos, subprocesos, errores, mensajes, llamadas,
versionado y migración, formularios y variables, asignación, segregación,
suspensión, acciones con reintentos e incidente, simulación, XXE, aislamiento,
auditoría, métricas, retención y RGPD), `tests/test_motor_bpmn.py`,
`tests/test_bpm_revision_2026_11_16.py`, `tests/test_bpm_i18n_codigos.py`,
`frontend/src/__tests__/BpmRunPanel.test.tsx`.

### Catálogo sembrado siempre al día (24-11-2026)

Al arrancar, la aplicación pone al día con el catálogo los procesos sembrados que nadie ha editado (su última versión
no tiene autor): crea una versión nueva con la nota «actualizado desde el catálogo». Si alguien editó el proceso,
no se toca. Antes un cambio del catálogo solo llegaba a una base existente sembrando con `force`.
Código: `bpmn_process_service.sincronizar_catalogo_sembrado` y `app/main.py::_sincronizar_catalogo_bpm`.
