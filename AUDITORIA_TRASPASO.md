# Auditoría de Contecflow PSA — estado y traspaso

Documento para retomar el trabajo desde otro equipo. Contiene el contexto
completo: qué se auditó, qué está cerrado, qué queda, cómo se verifica y las
reglas de trabajo que hay que respetar.

- **Tabla web viva:** https://claude.ai/code/artifact/7bf42ea8-c707-4dea-a8f9-f85991db3619
- **Rama:** siempre `main`. No hay ramas ni PRs en este proyecto.
- **Última actualización de este documento:** 2026-08-31

---

## 0. Reglas de trabajo (no negociables)

Son instrucciones del propietario del proyecto y aplican a todo lo que se haga
aquí:

1. **Nada de CI/CD.** No crear workflows, pipelines ni acciones. La verificación
   es local, con `scripts/ci_local.sh`.
2. **Todo sobre `main`.** Sin ramas, sin PRs. Commit y push directos.
3. **Commit y push al cerrar cada bloque**, sin esperar a que se pida.
4. **Al commitear, republicar la tabla web** en el mismo commit.
5. **Honestidad total.** Si algo no está hecho, se dice. No se declara completo
   lo que no lo está, no se maquillan métricas y no se afirma nada sin medirlo.
6. **Sin ñapas.** Configuración en `.env` **y** en la aplicación. Nada
   hardcodeado. Arquitectura de solución de primer orden, calidad de herramienta
   líder de mercado, todo documentado donde toque.

---

## 1. Cómo verificar (imprescindible antes de cualquier commit)

```bash
cd "contecflow PSA"

# Suite completa de backend: 3.467 tests recogidos. SIEMPRE con -n auto — en
# serie tarda MAS DE 90 MINUTOS y no cabe en ningun timeout razonable.
#
# TIEMPO MEDIDO con -n auto (10 workers): 36-43 MINUTOS (2.148 s y 2.551 s en
# dos pasadas del 2026-09-03, sobre 3.336 y 3.274 tests). Varia con la carga de
# la maquina. Si has leido en algun sitio "13 minutos" o
# "28 minutos", son cifras mias anteriores: la de 13 era falsa y la de 28 era
# cierta con 2.897 tests. El numero crece con la suite, asi que MIDELO en vez de
# creerte este. Importa: creyendo que tarda 13 se abandona la espera a los 20 y
# se commitea a ciegas, que es exactamente como una vez se dejo la suite en rojo
# sin detectarlo.
#
# Y NO edites app/ mientras corre. La suite recoge los tests al arrancar, asi
# que un cambio a mitad no se prueba y el "0 fallos" del final no cubre lo que
# has tocado. Es un error que he cometido en esta auditoria: hay que matar la
# ejecucion y relanzarla.
#
# Y NO lances dos sesiones de pytest a la vez. Con tres solapadas los workers
# se quedaron 22 minutos a 2,5 s de CPU cada uno — parecia un cuelgue del
# codigo y era contencion entre sesiones.
#
# Escribe la salida a un fichero en vez de a una tuberia (`| tail`): con tuberia
# no ves NADA hasta el final, ni el porcentaje ni un fallo.
./.venv/Scripts/python.exe -m pytest -q --no-header -p no:randomly -n auto > /tmp/suite.txt 2>&1

# Ojo al contar fallos en la salida: pytest solo escribe las lineas `FAILED` en
# el RESUMEN FINAL. Contarlas mientras corre da siempre cero, y eso no verifica
# nada. Mientras corre, los fallos se ven como `F` entre los puntos.

# Linter del backend: tiene que salir "All checks passed!"
./.venv/Scripts/python.exe -m ruff check app/

# Frontend
cd frontend
npx tsc --noEmit          # tiene que salir limpio
npm run test              # vitest
node scripts/check_i18n_coverage.mjs   # gate de cobertura de traducción

# Todas las puertas de golpe (10 bloqueantes + informativas)
bash scripts/ci_local.sh
```

**Estado en la última verificación completa (2026-08-31):**
**2273 passed, 17 skipped, 1 xfailed, 0 fallos** en 19 min con `-n auto`;
`ruff check app tests` limpio; `tsc` limpio; 89/89 vitest; los cinco gates de
frontend en verde.

> **Aviso sobre la verificación anterior.** El commit `b4ba85d` se hizo con la
> suite corriendo y su resultado nunca se reportó, porque en serie no terminaba
> dentro de ningún timeout. Dejó **tres tests en rojo** que no se detectaron:
> dos con la lista de ocho idiomas escrita a mano (obsoleta desde la reducción a
> tres) y el de paridad de Alembic, que reclamaba como faltantes los dos modelos
> que existen sólo para tests. Los tres están corregidos y de raíz — ver la
> sección 6. La lección: **un test que nadie termina de ejecutar no es una red.**

### Detalles que ahorran tiempo

- **La suite en serie tarda más de 90 minutos.** Con `-n auto` baja
  drásticamente. La razón: la fixture `db` de `conftest.py` es
  `scope="function", autouse=True` y **siembra la base en cada test**, así que
  cada caso parametrizado paga ese coste completo.
- `pytest --timeout=N` **no existe** en este proyecto (el plugin no está
  instalado). Usar `timeout` del shell.
- `tests/test_bi_metrics_catalog.py` en serie tarda ~9 min: son 133 casos
  parametrizados, cada uno resembrando la base.
- `pip install --dry-run` da falsos OK. Para dependencias, usar `pip check`.
- **No** ejecutar `ruff --select RUF100` en aislamiento: marca como inútil
  cualquier `noqa` de una regla no activada y destruye cientos de directivas
  legítimas. Usar `--extend-select RUF100`.
- Al escribir scripts con contrabarras o comillas, usar la herramienta de
  escritura de ficheros, no heredocs: se corrompen.

---

## 2. Lo que está cerrado

Todo lo de abajo está en `main`, verificado y con tests.

### P0 — 4 de 4

| # | Qué era |
|---|---|
| 1 | Un admin de tenant podía **desactivar y renombrar la organización de otro cliente**. Los endpoints de `/organizations` decían «super-admin» en su `summary` pero usaban `require_admin`, que es el rol de administrador *de tenant*. `require_superadmin` no existía en todo el repo. Eran **9 rutas** con `org_id` del cliente, no 5 como estimé al principio |
| 2 | El filtro de tenant de `TenantSession` era **fail-open**: ante cualquier excepción devolvía la consulta sin filtrar. Y `_can_access` devolvía `True` cuando el usuario no tenía organización, es decir acceso a cualquier tenant |
| 3 | `ABACMiddleware` **no se ejecutaba nunca**: leía `request.state.user`, que nadie poblaba, porque la autenticación vive en una dependencia de FastAPI y las dependencias se resuelven *después* de los middlewares |
| 4 | Subida de ficheros sin validación de profundidad; `collaboration/files.py` comprobaba el límite de 500 MB *después* de leer todo en memoria |

### P1 — 10 de 10, más #25 y #26

Incluye: ESLint sin parser de TypeScript (304 de 343 ficheros sin analizar y
`lint:a11y` informando «0 hallazgos» sobre ellos), `scripts/ci_local.sh`
evaluando el código de salida de `tail` en vez del de `pytest`, PKCE y `nonce`
del SSO, tareas asíncronas sin referencia fuerte, el endpoint
`/analytics/adhoc` (un `hasattr` sobre una función inexistente que devolvía
siempre `results: []`), y la matriz de permisos GRC, que era una pantalla de
administración escribiendo en una tabla que **nadie leía**.

### P2 — 7 de 7

| # | Qué se hizo |
|---|---|
| 11 | **Alembic como única fuente de verdad.** Al correr la cadena completa sobre una base vacía por primera vez: 374 tablas frente a 392 modelos → **faltaban 19** (`expenses`, `automation_rules`, `gdpr_requests`, `revenue_recognition_*`, `webhook_triggers`…). Revisión `089`. Ahora 393 tablas, 0 faltan, y hay un test de paridad |
| 12 | **Docker con la estrategia de contecmind/contecweb.** `docker-compose.yml` en raíz, 12 servicios, perfiles `app` y `observability`, volúmenes `external: true`, imágenes por digest, `beat` **fuera** del worker (con >1 réplica había varios planificadores disparando la misma tarea), nginx con proxy `/api` same-origin y WebSocket, `.dockerignore` nuevo, `AWS_S3_ENDPOINT_URL` configurable para MinIO |
| 13 | PKCE S256 + verificación de `nonce` |
| 14 | **Zonas horarias.** Ver sección 3 |
| 15 | Tareas asíncronas huérfanas y llamadas bloqueantes |
| 16 | **Tres idiomas en vez de siete a medias.** Ver sección 4 |
| 17 | Supresiones obsoletas y puertas de calidad |

### P3 — parcial, ver sección 5

---

## 3.ter #37 remedido: no son endpoints ausentes, son rutas equivocadas

La versión anterior de este documento decía «62 rutas del frontend que no
existen (7 corregidas, 9 identificadas como endpoints ausentes y 53 en código de
cliente muerto)». **Al volver a medirlo, el reparto es otro y cambia qué hay que
hacer.**

Medición: 851 rutas distintas que el frontend llama, cruzadas contra las rutas
reales de la aplicación normalizando los parámetros. Y para cada método
huérfano de `frontend/src/services/api/_core.ts`, se busca quién lo llama
**por su objeto exportado** (`sprintsApi.get`, no `get`), que es lo que decide si
es código muerto o una función rota de verdad.

> **Un aviso sobre la primera medición que hice hoy**, por si alguien repite el
> ejercicio: buscar el método por su nombre suelto da basura. Nombres como
> `get`, `create`, `update`, `delete` o `list` aparecen en todos los ficheros,
> así que salían «40 llamados» de los que la mayoría eran falsos. Hay que
> atribuir cada método a su objeto y buscar `objeto.metodo(`.

> **Y una corrección de mi propia medición, a mitad de hacerla.** La primera
> versión comparaba **sólo la ruta, ignorando el método HTTP**, así que
> `POST /sprints` parecía existir porque existe `GET /sprints`. Con método y
> ruta salen **42 huérfanos**, no 47, y el reparto cambia. Las cifras de abajo
> son las de la medición correcta.

| Categoría | Cuántos |
|---|---|
| Métodos que apuntan a un (método, ruta) inexistente | **42** |
| — inalcanzables: sólo los referencian hooks que nadie consume | **30** |
| — alcanzables desde una página o un hook vivo: **rotos de verdad** | **12** |

**La causa raíz es un cliente duplicado**, y el propio fichero ya lo comentaba en
un sitio: hay dos objetos para lo mismo, uno correcto y en uso y otro con la ruta
mal y sin usar. `projectSprintsApi` (12 métodos, todos correctos, lo usa
`SprintsPage`) frente a `sprintsApi` (8 de 9 rotos, no lo usa nadie);
`deliverablesApi.listByProject`/`overviewAll`/`createForProject` frente a
`list`/`overview`/`create`; `absencesApi.review`/`updateMy`/`deleteMy` frente a
`approve`/`reject`/`update`/`delete`. Los seis módulos de hooks que consumían las
versiones rotas —`useSprints`, `useExpenses`, `useOKRs`, `useDeliverables`,
`useAbsences`, `useTickets`— **no los importa ningún componente**: sólo los
reexporta el barrel `hooks/index.ts`. Comprobado uno a uno. Por eso nunca falló
nada: el código roto no se ejecutaba.

> **Aviso para quien repita la medida:** buscar el método por su nombre suelto da
> basura, porque `get`, `create`, `update`, `delete` o `list` aparecen en todos
> los ficheros. Hay que atribuir cada método a su objeto exportado y buscar
> `objeto.metodo(`. Y hay que seguir la cadena: un método que sólo usa un hook
> que nadie consume está muerto, aunque el hook lo referencie.

#### Hecho en esta tanda

* **Borrados 19 métodos** que no llamaba nadie y sólo podían dar 404
  (`authApi.syncLdap`, `risksApi.scores`, `absencesApi.get/update/balance`,
  `invoicesApi.get`, `assetsApi.cmdb`, `licensesApi.revoke`,
  `biAnomalyApi.predictChurn`, `trainingApi.cert`, `integrationsApi.jiraStatus`,
  `subcontractorsApi.get` y los cuatro de `slaSchedulesApi`).
* **Remapeados 6 de `subcontractorsApi`**: se les había caído el prefijo
  `/enterprise`, que su propio `list` sí llevaba. Verificado 1:1 contra la tabla
  de rutas, mismos parámetros.
* **`slaSchedulesApi` reescrito** a `/bookings/sla-schedules`, que es donde está
  el router; `update` y `delete` de un calendario no existen en el backend, así
  que se quitan en vez de dejarlos apuntando a nada.
* **Arreglado un fallo visible**: `dependenciesApi.get` pedía `/dependencies/{id}`
  cuando el router es `/task-dependencies/{project_id}`. Alimenta las
  dependencias del Gantt de proyecto, y la página trata la respuesta fallida como
  lista vacía, así que **el Gantt se dibujaba sin dependencias y sin error
  visible**. Es el único de los 12 alcanzables que tenía contraparte exacta.
* `npx tsc --noEmit`: **0 errores** después de todo lo anterior.

* **Borrados 29 métodos más y 24 funciones de hook** que sólo se referenciaban
  entre ellas: los ocho de `sprintsApi` (que `projectSprintsApi` sustituye), los
  cinco de `deliverablesApi` con gemelo correcto, los de `absencesApi` y
  `expensesApi` que duplicaban `review`/`updateMy`/`deleteMy`, y siete sueltos
  (`contractsApi.workOrders`, `okrsApi.get`, `trainingApi.course`,
  `ticketsApi.close`, `problemsApi.get`, `cmdbApi.getItem`, `cmdbApi.sdGet`).
  `hooks/useDeliverables.ts` se quedó sin ninguna función y se borró. Lo que
  apunta a rutas válidas se conserva intacto: de `useTickets` se fue 1 de 12, de
  `useExpenses` 3 de 12, de `useAbsences` 5 de 9.
* **`okrsApi.updateKR` corregido en vez de borrado**: el key result se identifica
  solo, el objetivo no va en la ruta. Completa un cliente de key-results cuyos
  `createKR`, `deleteKR` y `checkin` ya eran correctos.
* **Estado final medido: 42 → 11 huérfanos.** `npx tsc --noEmit` en 0 errores y
  `eslint` limpio en los ocho ficheros tocados, incluidos los imports que se
  quedaron sin uso al quitar las funciones.

#### Los 11 que quedan, y por qué no se tocan

Ninguno tiene contraparte: son endpoints que **no existen**, y hay un patrón —el
cliente ofrece «traer uno» o «borrar» donde el backend sólo implementó el listado
o el `PATCH`—:

| Método del cliente | Qué falta en el backend |
|---|---|
| `integrationsApi.exportImputations` / `exportProjects` | el prefijo `/integrations/export` no tiene **ni una** ruta |
| `trainingApi.updateCert` / `deleteCert` | `/training/certifications` sólo tiene `GET` y `POST` de colección |
| `contractsApi.get` / `workOrders` | `/contracts/{id}` tiene `PATCH` y `DELETE`, no `GET` |
| `risksApi.get` | `/risks/{proj}/{risk}` tiene `PATCH` y `DELETE`, no `GET` |
| `problemsApi.delete` | `/sd/problems/{id}` sólo tiene `PATCH` |
| `changesApi.delete` | `/sd/changes/{id}` tiene `GET` y `PATCH`, no `DELETE` |
| `pipelineApi.get` | no hay `GET /pipeline/{id}` |
| `sdKbApi.knownErrorTickets` | no hay `/sd/known-errors/{id}/tickets` |
| `oauthIntegrationsApi.delete` | `/oauth-integrations` sólo tiene `GET` y `POST` |
| `ticketsApi.close` | no hay `/sd/tickets/{id}/close`; se cierra por `PATCH` |

Implementarlos es decisión de producto: cada uno es un endpoint nuevo con sus
permisos y su semántica de borrado, no una corrección de ruta. **Son los 11
únicos que quedan**, y todos son alcanzables desde una página o un hook vivo, así
que cada uno es una función que hoy falla en la interfaz.

De ellos, dos merecen mención porque el fallo es silencioso igual que el del
Gantt: `problemsApi.delete` y `changesApi.delete` los llama
`ITSMKnowledgeTab`/`useChanges` para borrar, y el backend sólo implementó
`PATCH` — así que **el botón de borrar de un problema o de un cambio no borra
nada**. Lo que hay que decidir es si esas entidades deben poder borrarse o si el
cierre correcto es quitar el botón.

**Los duplicados rotos, con su contraparte correcta.** Esta tabla es la que
explica el defecto: el backend tiene la funcionalidad, en otro prefijo o con otra
forma, y el cliente muerto apuntaba al sitio equivocado:

| El cliente llama | El backend tiene |
|---|---|
| `/subcontractors`, `/subcontractors/{id}` … | `/enterprise/subcontractors/…` (22 rutas) |
| `/sla-schedules` | `/bookings/sla-schedules` |
| `/deliverables`, `/deliverables/overview` | `/deliverables/{project_id}`, `/deliverables/all/overview` |
| `/absences/{id}` (DELETE) | `/absences/my/{absence_id}` |
| `/absences/{id}/approve` y `/reject` | `/absences/{absence_id}/review` |
| `/expenses/{id}/approve` y `/reject` | `/expenses/{expense_id}/review` |
| `/okrs/{objId}/key-results/{krId}` | `/okrs/key-results/{kr_id}` |
| `/dependencies/{id}` | `/task-dependencies/{project_id}` |
| `/sprints/{id}/start`, `/burndown`, `/velocity` | `/sprints/{project_id}/sprints/{sprint_id}/…` |
| `/sprints/{id}/complete` | `/sprints/{project_id}/sprints/{sprint_id}/close` |

Quedan **sí ausentes de verdad**, y éstos son decisión de producto porque hay que
implementarlos: borrar un sprint, `PATCH`/`DELETE` de una certificación,
`/absences/policies`, cerrar un ticket por `/close`, los tickets de un error
conocido, borrar una integración OAuth y las dos exportaciones
`/integrations/export/imputations` y `/projects` —cuyo prefijo no tiene **ni una**
ruta registrada—.

**Lo que esto cambia del plan.** Arreglar el prefijo no siempre es un cambio de
una línea: varias rutas del servidor exigen `project_id` y el cliente hoy no lo
pasa, así que hay que cambiar la firma del método y sus llamantes, y en algún
caso el componente no tiene el proyecto a mano. Es trabajo por función, no un
barrido. Por eso queda medido y ordenado —19 borrables, ~18 remapeables, ~10 por
implementar— y no forzado en una tanda.

---

## 3.quater El hallazgo más grave de todos: **la columna de tenant que nadie rellenaba**

No lo buscaba. Salió al poner una guarda explícita de organización en
`endpoints/performance.py`, dentro del #22: los tests se pusieron en rojo y la
causa **no era la guarda**.

El filtro de tenant es `organization_id == org`. Una fila guardada con **NULL en
esa columna no la ve su propia organización**: sólo un superadmin. Y en el módulo
de evaluaciones **ninguna de las nueve creaciones la ponía**.

Medido con la sesión real de la aplicación:

```
performance_service.create_cycle()          -> organization_id = None
GET /performance/cycles  (usuario normal)   -> 0 ciclos
GET /performance/cycles  (superadmin)       -> 1 ciclo
```

**Se creaba el ciclo y desaparecía.** Editar o borrar una pregunta daba 404. Un
plan de desarrollo y sus objetivos, lo mismo. El módulo entero de evaluaciones
estaba muerto en un despliegue con tenant, y **no había un solo error en los
registros**: sólo listas vacías, que es exactamente lo que no se investiga.

#### Y no era un módulo: es sistémico

Barrido por AST de todo `app/`, contando construcciones de modelos que **tienen**
la columna y no son exentos ni globales:

| | |
|---|---|
| Modelos con `organization_id` (ni exentos ni globales) | **376** |
| Que se construyen **alguna vez** con ella | 170 |
| Que **nunca** se construyen con ella | **195** |
| Construcciones sin ella | **611** |

Segundo caso comprobado de punta a punta, y éste se ve desde la primera pantalla:

```
activity_service.notify()                   -> organization_id = None
GET /enterprise/notifications               -> 0 notificaciones
```

**El listado de notificaciones devuelve vacío.** Y con él el historial de
tickets, los comentarios de ticket, las imputaciones, las ausencias, los
sprints, las solicitudes de aprobación, los documentos… todo lo que se cree por
un camino que no sella la columna.

#### El arreglo: sellar en el `flush`, no parchear 611 sitios

Arreglar las 611 construcciones una a una sería perseguir el síntoma, y la
siguiente que alguien escriba vuelve a fallar. La causa es que **la organización
del sujeto de la petición no llega a la fila**, y el sitio donde eso se arregla
de una vez es el `flush`: `_sellar_organizacion` en `app/db/session.py`, un
escuchador `before_flush`.

Lo que hace y lo que **no** hace, porque los límites son la mitad del arreglo:

* Sella sólo objetos **nuevos** cuya `organization_id` sea `None`. **Un valor ya
  puesto no se toca nunca** — un superadmin que crea a propósito en otra
  organización sigue pudiendo.
* Sólo si la sesión tiene organización en `info`, que es lo que pone
  `get_current_user`. Un job de fondo o un script no la tiene, así que **su
  comportamiento no cambia**: siguen creando NULL como hoy.
* **No toca los modelos exentos** (`_tenant_exempt`) **ni los globales**
  (`_tenant_filter_include_global`). En `AppSetting` y en los ajustes de
  proveedor de IA un NULL significa «valor global del despliegue», y sellarlo lo
  convertiría en un ajuste de un solo cliente: los demás perderían su valor por
  defecto.
* Se desactiva con `TENANT_AUTO_STAMP_ON_INSERT=0`, igual que el filtro, para
  poder aislar un problema sin tocar código.

Verificado en seis casos: la notificación se sella y su usuario la ve; otra
organización no; un valor explícito se respeta; un `AppSetting` global no se
sella; un job de fondo no se sella; `Organization` es exenta.

Y para las filas **ya guardadas** del módulo de evaluaciones está
`alembic/versions/092_performance_backfill_organization.py`, que las hereda de su
padre —pregunta del ciclo, objetivo del plan— y las de las dos tablas sin padre
del usuario que las creó. Ejecutada contra una base con filas NULL: `None → ORG`
en las cuatro tablas. Sin `downgrade` que borre datos, y dicho por qué.

> **Lo que queda abierto de esto, y es una decisión, no un olvido:** el
> escuchador está registrado sobre `SessionLocal`, así que **la suite no lo
> ejercita** — igual que no ejercita el filtro de tenant (§3.bis). Su
> verificación son los experimentos de arriba y
> `tests/test_sellado_de_organizacion.py`, que lo engancha a mano. Registrarlo
> en la factoría de los tests haría que la suite entera trabajara con la
> semántica de producción, que es lo correcto a medio plazo, y cambia lo que ven
> los tests que hoy crean filas sin organización. Es el mismo trabajo pendiente
> que el del filtro, y ahora hay dos razones para hacerlo.
>
> **Y las 611 construcciones siguen sin poner la columna.** El sellado las cubre
> en el camino de peticion, que es donde importa, pero un job de fondo que cree
> una fila la seguira dejando en NULL. Bajar esa cifra es trabajo aparte y
> ahora, con el sellado puesto, ya no es urgente.

---

## 3.quinquies El portal de cliente corría con el aislamiento por organización **apagado**

Salió al mover a servicio las tres consultas del selector de contexto de
`dynamic_forms.py`, que es alcanzable desde el portal. Al preguntarme «¿y aquí
qué organización filtra?», la respuesta fue: ninguna.

`get_current_client` autentica al usuario del portal por su token, devuelve su
fila y **nunca poblaba `db.info`**. Y las tres capas de aislamiento de
`TenantSession` —`query()`, `execute()` y el escuchador `do_orm_execute`— salen
por la puerta de atrás cuando `info` no trae `is_superadmin`. Esa rama existe
para los trabajos de fondo y los tests («sesión no inicializada»), no para una
petición autenticada de un cliente externo.

**41 dependencias de endpoints** cuelgan de `get_current_client`. Medido con la
sesión real de la aplicación, no razonado:

```
portal SIN contexto  ->  db.query(Client)  devuelve  ['ORG-A', 'ORG-B']
portal CON contexto  ->                    devuelve  ['ORG-A']
```

Es el mismo defecto que el WebSocket del chat, que también fabricaba su sesión a
mano y la dejaba sin contexto, pero mucho mayor por el número de endpoints que
cuelgan de aquí. **Y es el contrario del apagón de §3.bis:** allí el filtro
existía y dejaba a ciegas a todos los clientes menos al primero; aquí no había
filtro de ninguna clase.

El arreglo va en un solo sitio y **después** de resolver al cliente:
`get_active_client_by_id` busca por id sin saber todavía de qué organización es,
así que esa consulta tiene que correr sin filtrar. La misma ordenación que hizo
falta en el WebSocket:

```python
db.info["organization_id"] = getattr(client, "organization_id", None)
db.info["is_superadmin"] = False
db.info["current_client"] = client
return client
```

`tests/test_portal_contexto_de_tenant.py` engancha el filtro de producción a la
sesión de pruebas a mano —la suite usa otra factoría, así que no se dispara en
ningún test— y comprueba tres cosas: que el escenario de antes era real, que con
contexto sólo se ve una organización, y que la dependencia entera publica el
contexto. Ese último es el que impide que vuelvan a quitarse las tres líneas.

**Además, el filtro explícito.** Las tres consultas del selector (`ServiceItem`,
`Client`, `ConfigurationItem`) ahora acotan por la organización del sujeto, sea
un usuario interno o del portal. Depender sólo del filtro implícito es lo que
hizo que este defecto no se viera: un fallo en una capa lo dejaba todo abierto.

### Cuatro catálogos globales que mi propio sellado habría privatizado

El sellado en el `before_flush` de §3.quater rellena `organization_id` en toda
fila nueva que no lo traiga. Antes de darlo por bueno fui a buscar qué filas se
crean **a propósito** sin organización, y aparecieron cuatro:
`IntegrationConnector`, `CustomProjectType`, `CustomProjectStatus` y
`CustomTaskStatus`. Son catálogos que trae el producto, sembrados de forma
perezosa desde un camino de petición (`if count() == 0: sembrar()`), así que la
primera organización que abriera la pantalla los habría sellado como suyos y
**habrían desaparecido para todas las demás**.

Los cuatro declaran ahora `_tenant_filter_include_global = True`, que ya existía
para esto: el filtro pasa a ser `org == X OR org IS NULL`. Comprobado con las
dos organizaciones: el catálogo sembrado desde ORG-A se queda en `{None}`, las
dos ven los 22 conectores, y ORG-A ve 23 cuando añade el suyo mientras ORG-B
sigue viendo 22.

**La lección, que es la que importa para el resto del sellado:** un arreglo de
raíz sobre 611 sitios de creación necesita saber cuáles de esos sitios *quieren*
la columna vacía. Sin esa comprobación, el arreglo del aislamiento habría roto
el catálogo del producto — y el modo de fallo habría sido «a un cliente le
faltan tipos de proyecto», que nadie relaciona con un `before_flush`.

## 3.bis Hallazgo grave encontrado al cerrar el #22: **el filtro de tenant dejaba a ciegas a todos los clientes menos al primero**

No lo buscaba. Apareció escribiendo un test que necesitaba el filtro global de
aislamiento por organización activo, y es lo más serio de toda la tanda.

> **Corrección importante de mi primer diagnóstico.** Lo describí como una fuga
> entre tenants, y **no lo es**. Lo era en el experimento con el que lo
> encontré, que usaba una `Session` plana; con la clase de sesión real de la
> aplicación el efecto es distinto y hay que decirlo con precisión. Las cifras y
> el veredicto de abajo son los de la medición correcta, con `TenantSession`.

`app/db/session.py` monta el aislamiento multi-tenant (auditoría #C5) como un
escuchador de `do_orm_execute` que engancha un criterio por modelo. El criterio
estaba escrito así:

```python
_with_loader_criteria(
    model,
    lambda cls, _org=org_id: cls.organization_id == _org,   # ← argumento por defecto
    include_aliases=True,
)
```

**La organización iba en un argumento por defecto.** El sistema de lambdas de
SQLAlchemy analiza las **variables de cierre** de la lambda para convertirlas en
parámetros ligados; los argumentos por defecto no: se evalúan una vez, al crear
la lambda, y quedan cocidos en la sentencia compilada. Esa sentencia se guarda
en la caché del *engine*, que es **de proceso y compartida por todas las
peticiones**.

Consecuencia: la primera organización que ejecuta una forma de consulta fija el
valor para todo el proceso. Con una `Session` plana —sólo el escuchador
filtrando— eso **devuelve las filas de la primera organización a la segunda**:

```
sesión 1 (ORG-A) → ['ORG-A']
sesión 2 (ORG-B) → ['ORG-A']      ← datos de otro tenant
```

**Pero la aplicación no usa una `Session` plana.** `SessionLocal` usa
`TenantSession`, que sobrescribe `query()` **y** `execute()` y añade el filtro
correcto con una expresión directa, no con una lambda cacheada. Esas dos
sobrescrituras son la capa primaria y **funcionan bien**. El escuchador es una
tercera capa de respaldo. Medido con `TenantSession`, que es lo que corre:

```
escuchador DEFECTUOSO:  ORG-A → ['ORG-A']   ORG-B → []          ORG-A → ['ORG-A']
escuchador CORREGIDO:   ORG-A → ['ORG-A']   ORG-B → ['ORG-B']   ORG-A → ['ORG-A']
```

Es decir: el filtro correcto de la capa primaria y el criterio rancio del
escuchador se suman con **organizaciones distintas**, y el resultado es un
`WHERE org = 'ORG-B' AND org = 'ORG-A'` que no devuelve nada. **No es una fuga:
es un apagón.** La primera organización que pasa por cada forma de consulta se
queda con ella, y todas las demás ven cero filas en esa consulta durante la vida
del proceso. Una sola organización nunca lo delata — hacen falta dos seguidas en
el mismo proceso.

Que sea un apagón y no una fuga lo hace menos grave en confidencialidad y más
visible en operación, pero no lo hace aceptable: el control no hacía lo que dice,
y la capa de respaldo llevaba a cero el trabajo de la primaria.

Se comprobaron las tres formas posibles del criterio antes de elegir:

| Forma | ORG-A → ORG-B → ORG-A |
|---|---|
| `lambda cls, _org=org_id:` (la que había) | A, **A**, A — filtra mal |
| `lambda cls: ... org_id` (variable de cierre) | A, B, A — correcto |
| `model.organization_id == org_id` (sin lambda) | A, B, A — correcto |

Se usa la variable de cierre: es la forma documentada, SA la extrae como
parámetro ligado y no infla la clave de caché con un valor por organización.

**Y un segundo defecto en la misma función, en la rama de al lado.** El caso
«usuario normal sin organización» decía en su comentario *«block any data
return»* y hacía esto:

```python
_with_loader_criteria(object, lambda cls: _sql_false(), include_aliases=True)
```

Pasar `object` como objetivo hace que SA recorra `object.__subclasses__()` hasta
llamar a `type.__subclasses__()` sin instancia:

```
TypeError: unbound method type.__subclasses__() needs an argument
```

Así que no bloqueaba: **reventaba cualquier consulta ORM de esa sesión** con un
500. Se llega ahí con un usuario sin organización asignada y también con un
simple refresco de atributos antes de que la sesión tenga su `organization_id`
—que es cómo lo encontré—. Ahora usa el mismo mecanismo que el filtro normal,
un criterio `false()` por modelo.

> **El primer arreglo que escribí para esto estaba mal y lo cazó el test.** Puse
> `execute_state.statement = execute_state.statement.where(false())`, que
> funciona aislado y falla acompañado: una modificación directa de la sentencia
> **no entra en la clave de la caché** de sentencias compiladas, mientras que
> las opciones de criterio sí. La SQL con `WHERE false` se reutilizaba después
> para la misma consulta con organización válida y devolvía cero filas. Es el
> mismo error de fondo que el defecto original: suponer que lo que se le hace a
> la sentencia viaja con ella.

#### Y el gate que debía vigilar esto estaba muerto

`scripts/audit_tenant_isolation.py` marca las consultas de `app/services` sin
ámbito visible y las compara contra `scripts/tenant_audit_baseline.txt`, 2.334
líneas ya revisadas. Tres cosas:

1. **El identificador interpolaba el `Path` directamente**, y en Windows eso
   serializa con barra invertida mientras el baseline se escribió con `/`. Ni una
   línea coincidía, así que `--strict` daba `STRICT FAIL` con los 2.334 hallazgos
   conocidos marcados como nuevos. **Un gate que no puede pasar nunca no informa
   de nada.** Arreglado con `as_posix()`.
2. **Faltaba `_org(` en las pistas de ámbito.** Es el ayudante real de este
   repositorio —devuelve la organización del sujeto y lanza 403 si no tiene—, así
   que toda consulta acotada con él se marcaba como sospechosa.
3. **La ventana era fija, `lines[i-3:i+3]`.** Una consulta encadenada
   —`db.query(X)` en una línea y `.filter(X.organization_id == …)` cuatro más
   abajo, que es el estilo de casi todo el repositorio— dejaba el filtro fuera de
   la ventana. Medido sobre `app/services/collaboration`: **93 de 118 avisos eran
   ese falso positivo**. Ahora la ventana es la sentencia completa siguiendo el
   balance de paréntesis, con un suelo de tres líneas para que domine
   estrictamente a la anterior y el cambio no pueda hacer aparecer avisos nuevos.

**Lo que queda y por qué no se sigue afinando.** Con el detector arreglado siguen
marcadas ~2.350 consultas, y al revisar la muestra de `collaboration` una a una
el resto son **acotación por una clave padre que ya está acotada**
—`workspace_id`, `team_id`, `conversation_id`— o por `user_id`, que es un ámbito
**más estrecho** que la organización. El heurístico no puede verificar eso, y su
propio docstring dice que es «a review aid, not a strict proof». Bajar el número
metiendo esas claves en las pistas debilitaría el gate: un `workspace_id` que
viene del cliente sin comprobar es justamente el defecto que debe cazar. Así que
se deja el detector correcto y el número honesto, en vez de perseguir la cifra.

De la revisión sí salieron **tres consultas propias que merecían filtro explícito
de organización**: `_usuarios_por_id` y las dos resoluciones de conversación de
`conversation_detail`, en `services/collaboration/workspaces.py`. Dependían del
filtro global —el que estaba roto—, y aunque en una petición real el ámbito llega
por la clave padre, el filtro explícito es defensa en profundidad y cuesta una
línea. Pendiente de aplicar al cerrar esta tanda.

> Las otras tres que el gate marca en ese fichero —`mark_all_notifications_read`,
> `mark_notification_read` y `registrar_uso_de_busqueda`— **están bien y no se
> tocan**: filtran por `user_id == user.id`, que es un ámbito más estrecho que la
> organización. Añadirles el filtro de organización no cambiaría nada.

#### Hueco de cobertura que esto destapa, y que sigue abierto

**Precisión, porque la primera versión de este párrafo era demasiado gruesa.** La
suite *sí* tiene pruebas de aislamiento: `test_tenant_filter_coverage.py`
comprueba que los 392 modelos tienen una vía de filtrado declarada o una exención
con motivo, y `test_tenancy_isolation.py` e `test_invoice_tenant_isolation.py`
prueban el aislamiento a nivel de endpoint. Lo que **ninguna** prueba ejercita es
el **escuchador `do_orm_execute`**: se registra sobre `SessionLocal` y
`tests/conftest.py` usa otra factoría (`TestSession`, SQLite en memoria), así que
no se dispara en ningún test. Por eso ni el apagón ni el `TypeError` los vio
nunca nadie: esa capa está escrita, documentada y **sin ejercitar**.

Los dos tests nuevos enganchan el escuchador a la sesión de pruebas a mano para
reproducir la condición real (`tests/test_tus_push_calendario.py`, los dos
`test_EL_HALLAZGO_..._tenant...`). Eso cubre estas dos ramas, no el mecanismo
entero. **Registrar el filtro en la factoría de tests es una decisión con
consecuencias** —pasaría a filtrar en toda la suite y hay tests que hoy leen
entre organizaciones sin declararlo— así que no se toca de paso: queda anotado
como trabajo propio.

---

## 3. Hallazgo grave encontrado durante el #14 (cerrado)

Al encaminar las fechas apareció algo peor que el propio #14.

**`_recognize_over_time` en `app/services/revenue_service.py` reconocía cero
euros, siempre.** Leía la tarifa así:

```python
avg_rate = getattr(proj, "hourly_rate", None) or getattr(proj, "daily_rate", None) or 0.0
```

Ninguno de esos dos campos existe en `Project` — el real es `billing_rate`. Con
los dos `getattr` llevando valor por defecto no lanzaba nada: la tarifa valía
0.0, el importe 0.0 y el `if recognized > 0` no entraba nunca. **Verificado
ejecutando el lote: 0 asientos.** El reconocimiento ASC 606 / IFRS 15 de T&M y
consumo llevaba sin reconocer un euro, sin un error en los registros.

Dos defectos más en la misma función de 40 líneas:

- **No era idempotente**: no comprobaba si ya existía asiento para (contrato,
  periodo). Un reintento de Celery, un disparo manual o —hasta el arreglo del
  #12— varios `beat` simultáneos duplicaban los ingresos hasta agotar el valor
  del contrato. Su hermana `_recognize_straight_line`, 40 líneas más abajo, **sí**
  lo comprobaba: fue un olvido.
- **No filtraba `is_approved`** aunque su docstring decía «approved imputation
  hours».

El primero mantenía latente el segundo: como nunca creaba nada, nada podía
duplicarse. Arreglar el primero sin el segundo habría convertido un módulo
muerto en uno que inventa ingresos.

**Arreglado:** los tres, `_ya_reconocido` compartido entre las dos vías, acceso
directo al atributo (sin `getattr` con defecto, para que un renombrado futuro
falle en voz alta), aviso explícito cuando un proyecto no tiene tarifa, e índice
único **parcial** en `rev_entries` (revisión `091`).

> **El índice tiene que ser parcial.** Mi primer diseño —único sobre (contrato,
> año, mes, tipo)— **habría roto producción**: el reconocimiento por hitos crea
> varios asientos `recognized` del mismo periodo, uno por obligación satisfecha,
> y las reversiones comparten periodo con su origen. El filtro es
> `milestone_id IS NULL AND entry_type = 'recognized'`, que son exactamente las
> filas del lote mensual. Hay un contra-test que se pone rojo si alguien le quita
> la cláusula.

El planificador también estaba mal: `crontab(day_of_month=1, hour=2)` disparaba
a las 02:00 UTC, cuando en UTC−6 es todavía el día 31, así que su «mes anterior»
salía desplazado un mes y el mes que acababa de cerrar **no se reconocía nunca**.
Ahora corre a diario y actúa sobre cada organización en su día 1 — seguro sólo
porque el lote ya es idempotente. `run_monthly_recognition` acepta
`organization_id` para no recorrer los contratos de todas las demás en cada
llamada.

Era además el mayor módulo de la solución **sin ningún test**. Ahora tiene 10
en `tests/test_revenue_idempotency.py`.

---

## 3.b Dos defectos de seguridad encontrados al partir funciones complejas

Ninguno de los dos estaba en la auditoría inicial y ninguno se buscaba:
aparecieron al poner el código de una función compleja en piezas con nombre, que
es cuando una asimetría deja de esconderse. Los dos son el patrón de la sección
5: el control cuidadoso existe y hay una segunda vía que lo salta, o un respaldo
tolerante que convierte un fallo en la acción equivocada.

### Un empleado podía elegir quién aprueba sus propias solicitudes

`PATCH /users/{user_id}` usa `get_current_user`, **no** `require_admin`: una
persona puede editar su propia ficha por ahí, y con el esquema **ancho**
(`UserUpdate`). Los campos se aplicaban con un bucle genérico:

```python
for field, value in payload.model_dump(exclude_unset=True).items():
    setattr(user, field, value)
```

y la guarda sólo protegía `role` y `hourly_rate`. Quedaba fuera `manager_id`.

`manager_id` **es una entrada de autorización**: un paso de aprobación con
`approver_type == "manager"` autoriza a quien sea `requester.manager_id`
(`approval_engine/_base.py:177`). Y la plantilla de flujo **por defecto** trae
ese paso como el primero, llamado «Direct Manager» (`_base.py:55`), así que es
alcanzable en configuración estándar.

Por esa vía se saltaban además las tres validaciones del endpoint dedicado:

| | `PATCH /users/{id}/manager` | `PATCH /users/{id}` genérico |
|---|---|---|
| Autorización | `require_admin` | `get_current_user` |
| El manager existe | sí | **no** |
| Misma organización | sí | **no** |
| Ciclos en la jerarquía | sí | **no** |

`status` quedaba igual de libre.

**Arreglo.** Quien no es administrador sólo puede cambiar de su propia ficha los
campos que la aplicación ya declara autoeditables: los de `UserSelfUpdate`, el
esquema del endpoint `/users/me`. **Se derivan de ahí, no de una lista escrita a
mano** — una lista paralela se separaría al primer campo nuevo, y el que se
olvidara quedaría abierto sin que nada fallara. Hay un test que cruza las dos y
otro que comprueba que ningún campo de autorización acabe marcado como
autoeditable.

Es más estricto que antes en un punto, y a propósito: la guarda antigua miraba
`payload.role is not None`, así que `{"role": null}` la pasaba. Ahora cuenta lo
**enviado**, no lo enviado con valor — borrar tu propio manager también es
cambiar quién aprueba tus solicitudes.

**Lo que no se ha tocado y conviene mirar:** `PATCH /users/{user_id}` sigue
aceptando el esquema ancho para todo el mundo, y el filtro está en el servicio.
Sería más limpio que el endpoint eligiera el esquema según el actor, pero eso es
un cambio de contrato de la API y no de un refactor.

### La rotación programada podía corromper el secreto OIDC y los de webhook

`_rotate_integration_secrets` recorre cinco modelos recifrando secretos. Tres
llevaban un respaldo «esto es texto en claro heredado, cifrémoslo»:

```python
if plain:                            # recifrar
elif not valor.startswith("v2:"):    # tratar como plaintext y cifrar
```

SSO y webhooks comprobaban sólo `v2:`; `AppSetting` comprobaba `v2:` **y**
`kmsv1:`. La asimetría no era intencionada.

Y la rama es **inalcanzable para su propósito declarado**: `decrypt_value()` ya
devuelve el texto plano cuando el valor es plaintext heredado —lo hace su propio
respaldo interno—. Comprobado por ejecución:

```
decrypt_value("clave-en-claro") -> 'clave-en-claro'   <- entra por `if plain`
decrypt_value("v2:sin-punto")   -> None
decrypt_value("kmsv1:AAAA")     -> None               <- el caso corruptor
```

Lo único que llega al `elif` es un valor cuyo descifrado **falló**. Con
`KMS_PROVIDER=aws`, un secreto `kmsv1:` y KMS momentáneamente inalcanzable:
`decrypt_value` devuelve `None`, el valor no empieza por `v2:`, y **se cifra el
criptograma**. Queda cifrado dos veces e irrecuperable sin descifrar dos
niveles. `AppSetting` se salvaba sólo porque su comprobación incluía los dos
prefijos.

Lo dispara la rotación programada, así que ocurriría sin que nadie lo pidiera y
a la hora en que nadie mira. El síntoma sería que el SSO deja de funcionar para
el tenant y los webhooks dejan de validar firma, con el secreto original ya
perdido.

**Arreglo.** Se recifra **sólo** cuando el descifrado ha funcionado. Un valor
ilegible se deja intacto y se avisa con el modelo, el identificador y el campo —
nunca el valor, y hay un test que comprueba que el secreto no aparece en el log.
Dos tests estructurales cruzan la tabla de modelos y campos con los modelos
reales: un nombre de campo mal escrito haría que ese secreto no se rotara nunca,
en silencio, porque el acceso es por `getattr` con respaldo.

**Si esto ya ha pasado en algún despliegue** —secreto OIDC cifrado dos veces— la
recuperación es descifrar dos niveles con la clave que estuviera activa
entonces. No hay migración automática porque no se puede distinguir un
criptograma doble de uno simple sin intentarlo, y hacerlo a ciegas sobre todos
los secretos es peor que el problema. Lo razonable es comprobar que el SSO y los
webhooks siguen funcionando y, si no, reintroducir el secreto a mano.

### Y una función que decidía aprobaciones sin un solo test

`_check_auto_approval` (complejidad 18) decide si una solicitud se aprueba **sin
revisión humana**, y buscando `auto_approval`, `_check_auto_approval` o
`auto_approve` en todo `tests/` **no aparecía nada**. Misma clase de hallazgo que
el middleware ABAC muerto (#2) y las reglas de enrutado de tickets (#18).

Lo que sus 26 tests nuevos fijan y no estaba fijado:

- una regla de auto-aprobación **sin condiciones no aprueba nada**. Si «ninguna
  condición» contara como «todas cumplidas», una regla mal configurada aprobaría
  absolutamente todo sin que nada fallara;
- las condiciones de importe son **estrictas** en las dos direcciones: un importe
  igual al umbral no cumple ni `amount_lt` ni `amount_gt`;
- las condiciones de una regla se combinan con **Y**, no con **O**;
- la **asimetría deliberada** entre los dos evaluadores de condiciones: un
  importe ilegible hace que la auto-aprobación **no** aplique, y que la condición
  de un paso lo deje **activo**. Las dos fallan hacia pedir una firma humana, y
  uniformarlas «para que sean coherentes» volvería insegura una de las dos. Hay
  un test dedicado sólo a eso;
- que las cuatro condiciones que el esquema `AutoApprovalRuleConditions` declara
  estén **todas implementadas**: una declarada y no implementada se ignoraría en
  silencio, el administrador la configuraría, y la regla aprobaría sin
  comprobarla.

---

## 3.c Tres defectos funcionales encontrados al partir funciones complejas

Ninguno de los tres daba error en la suite antes de tocarlos. Los tres se vieron
al preguntar, línea por línea, qué tiene que pasar para llegar a cada rama.

### Una factura de 29 líneas o más no se podía generar

`app/services/invoice_pdf.py`. La tabla de conceptos llevaba

```python
("NOSPLIT", (0, 0), (-1, -1))
```

que en ReportLab significa «esta tabla no se puede partir por ninguna parte». La
intención era otra: que el bloque de totales —base, IVA y total— no quedara
separado de las líneas. Aplicado a la tabla entera **prohíbe todo salto de
página**, así que en cuanto los conceptos no caben en una hoja `reportlab` lanza
`LayoutError` y la factura no se genera.

> **CORRECCIÓN a lo que escribí primero.** Dije que «el usuario recibe un 500».
> **No era cierto**, y lo descubrí después: este generador estaba detrás de
> `GET /billing-reports/invoices/{id}/pdf`, una ruta que **no llamaba nadie**.
> La interfaz descargaba la factura por `/invoices/{id}/pdf`, que era **otro
> generador entero**, dibujado a mano — así que el usuario sí recibía un PDF, y
> el problema real de esa vía era peor: le faltaban los datos fiscales. Ver el
> apartado siguiente. El defecto del `NOSPLIT` era real, pero su impacto
> user-visible **no** era el que le atribuí.

Y hacía **inerte el `repeatRows=1`** que está dos líneas más arriba: repetir la
cabecera en cada página no tiene sentido si no puede haber una segunda página.
Dos ajustes que se contradecían, y el que ganaba era el que rompía.

Arreglado acotando el `NOSPLIT` a las tres filas de totales:

```python
# NOSPLIT SOLO sobre el bloque de totales, no sobre la tabla entera.
("NOSPLIT", (0, n + 1), (-1, n + 3)),
```

**Cuidado al verificar un PDF:** los bytes no pueden coincidir entre dos
generaciones, porque ReportLab escribe la fecha de creación y un identificador
aleatorio en cada documento. La comparación tiene que ser sobre el **texto
extraído, el número de páginas y la longitud**. Y el umbral de 29 líneas
**depende de la altura del bloque de cliente**: dos tests míos estaban mal por
haberlo medido sin ese bloque. La cabecera de
`tests/test_invoice_pdf_layout.py` dice en qué condiciones se midió.

### Dos generadores de factura, y el que usaba la interfaz no era el bueno

Esto salió al cablear la marca (hallazgo 32) y es **lo más grave de la sesión**.

Había **dos** implementaciones independientes del PDF de factura:

| | `app/services/invoice_pdf.py` | `app/api/v1/endpoints/invoices.py` |
|---|---|---|
| Ruta | `GET /billing-reports/invoices/{id}/pdf` | `GET /invoices/{id}/pdf` |
| ¿Quién la llamaba? | **nadie** — ni el frontend ni otro módulo | **la interfaz**: `_core.ts` → `api.get('/invoices/${id}/pdf')` |
| Trazado | tabla, paginación, cabecera repetida, paleta | 70 líneas a mano con `rl_canvas` |
| NIF del cliente | **sí** | **no** |
| Dirección del cliente | sí | no |
| Nombre del emisor | sí | no |
| Referencia de pedido, periodo, notas | sí | no |
| Descripción de línea | completa | **truncada a 50 caracteres** (`[:50]`, silencioso) |

**Una factura sin la identificación fiscal de las dos partes no es una factura
válida.** El documento por el que se cobra, el que descargaba el usuario, no
llevaba el NIF del cliente ni el nombre del emisor. Y el `[:50]` cortaba el
concepto sin ningún aviso.

De paso, esto explica la corrección del apartado anterior: **todo el trabajo de
trazado de `invoice_pdf.py` vivía en una ruta que nadie pedía**, el arreglo del
`NOSPLIT` incluido.

**Resuelto** haciendo que `/invoices/{id}/pdf` delegue en `generate_invoice_pdf`.
Se van 72 líneas de duplicado y llegan de golpe los datos fiscales, el trazado,
la paginación y la marca del tenant. Se conserva lo propio de esa ruta: el 403
por rol, el 404 y la descarga como adjunto con el nombre saneado, cada uno con
su test.

**La lección, que vale más que el arreglo:** dos implementaciones de lo mismo no
divergen en calidad por igual — una recibe todo el mantenimiento y la otra
ninguna, y **la que se usa puede ser la abandonada**. Antes de invertir en
mejorar un generador, comprobar quién lo llama. Se comprueba en un minuto:

```bash
grep -rn "invoices/.*pdf" frontend/src/services
```

---

### El nodo «crear ticket» de los flujos de trabajo no podía funcionar nunca

`app/services/service_desk/workflow_engine.py`. Dos cosas a la vez:

- construía el `Ticket` con `description` obligatorio en el modelo y el valor
  que le llega de la plantilla, que es **opcional** — así que un nodo sin
  descripción reventaba en el `flush`;
- y el `except` **no hacía `rollback()`**, de modo que la sesión quedaba en
  transacción abortada y **todo lo que venía después del nodo fallaba también**,
  incluido el registro del propio error.

Arreglado con `description = ... or title` y el `rollback()` que faltaba. La
lección del segundo punto es general y aplica a todo el repo: **un `except` que
sigue tras un `flush` fallido necesita `db.rollback()`**, o convierte un fallo
local en un fallo de todo lo que venga detrás.

### Un tipo de nodo que el diseñador deja guardar y el motor no ejecuta

Décima instancia del patrón. El tipo `action` pasa la validación del diseñador
de flujos, se guarda y se dibuja — y **no tiene ejecutor**. El flujo se queda
parado en ese nodo sin decir por qué.

El motor exporta ahora `TIPOS_EJECUTABLES` y `validate_graph` avisa **al
guardar**, no cuando el flujo ya está en producción. El aviso se hace con import
diferido para no crear un ciclo entre el diseñador y el motor.

**No se ha implementado el ejecutor de `action`**, y es deliberado: qué debe
hacer ese nodo es una decisión de producto, no un hueco que rellenar. Lo que no
podía seguir es que se guardara en silencio.

---

## 3.d Doce importes diferidos que apuntaban a cosas que no existen

**Lo más productivo de la auditoría, y salió de un aviso de log de refilón.** Al
probar el generador de informes programados apareció en la salida:

```
PostgreSQL utilization fallback failed: cannot import name 'Resource'
```

Un `import` **dentro de una función** no revienta al arrancar: falla la primera
vez que alguien la llama. Y si además está dentro de un `try/except`, no falla
nunca de forma visible — sólo degrada. Esa combinación produjo **doce funciones
que no podían funcionar**, y varias en completo silencio.

| Sitio | Qué importaba | Efecto real |
|---|---|---|
| `olap/query_engine.py:304` | `Resource` de `app.models.resources` — **no existe en el repo** | el **Informe de Utilización salía siempre vacío**: el `ImportError` era la primera línea del `try`, así que ni una consulta llegaba a ejecutarse |
| `integrations.py:541` | `SlackConfig` de `app.models.slack` — el módulo no existe (está en `mfa`) | `get_slack_webhook_url` devolvía **siempre `None`** y el `except ImportError: return None` lo explicaba como «no configurado». **Las notificaciones de Slack no salían nunca**, con datos válidos sembrados |
| `integrations.py` | `test_quickbooks_connection` — **nunca se escribió**; su gemela `test_xero_connection` sí | `POST /accounting/qb/test`, «Verificar conexión con QuickBooks», **siempre 500** |
| `customer_health_service.py:124` | `PortalSession` — **no existe** (el modelo es `ClientSession`) | el componente «actividad en el portal» valía **50,0 constante para todos los clientes**: uno de los cinco factores del score compuesto de salud era un número fijo |
| `worker.py:581`, `:630` | `app.models.client` — el módulo es `clients`, en plural | fallo en tiempo de llamada |
| `worker.py:745` | `get_default_provider` del módulo de **endpoints**, que no lo define | el camino de agentes fallaba en cada ejecución. Está en `ai_provider_service`, y de paso desaparece una dependencia worker→API que no debía existir |
| `capacity_planning_service.py:164`, `sd_reporting_service.py:146` | `app.models.auth` — no existe (es `user`) | dos informes de service desk que **fallaban en cada llamada** |
| `predictive_observability.py:56` | `Organization` de `enterprise` (está en `mfa`) | la comprobación **anti-enumeración de IDs** lanzaba `ImportError` en vez de validar |
| `bi_report_delivery_service.py:434` | `app.services.email_service` | el envío **sí funcionaba** por el respaldo SMTP, pero registraba «Primary email_service path failed» con traza completa **en cada correo**. Un aviso que no es un aviso entierra los que sí lo son |

### El arreglo del score de portal tenía una trampa

`PortalSession` era `ClientSession`, pero **cambiar sólo el nombre no bastaba**:
`ClientSession.client_id` apunta a `client_users.id`, **no** a `clients.id`, y la
función recibe un `Client.id`. Arreglar sólo el import habría cambiado «siempre
50» por «siempre 0 sesiones» — igual de falso y más difícil de detectar. La
cadena real es `Client.id` ← `ClientUser.client_org_id` ← `ClientSession.client_id`,
y de ahí el `join`.

Y el `hasattr(PortalSession, "client_id")` que había era una defensa muerta:
sobre un modelo declarado siempre es verdadera.

### El del informe de utilización quitó además una consulta por usuario

La capacidad que buscaba en `Resource` vive en `User.weekly_capacity_hours`, con
su defecto en `settings.DEFAULT_WEEKLY_CAPACITY_HOURS` — es lo que usan los otros
cuatro sitios del repo que calculan capacidad. Al leerla en la consulta principal
desaparece el `db.query(Resource)` **dentro del bucle**: una consulta por usuario.
También se retira el `40` en duro.

### Tres que NO se implementan, y están registrados

`record_sla_event`, `notify_watchers` y `quick_answer` no existen, y sus
comentarios decían «if available» / «may not exist» — que se lee como una
condición de ejecución y era «no está escrito». Consecuencias reales: **el evento
de cierre de SLA de una auto-resolución nunca se registra**, **a los observadores
de un ticket nunca se les avisa** de que la IA lo resolvió, y **la vía de IA del
bot Nexus nunca responde**.

No se implementan porque son decisiones de producto —qué evento de SLA
corresponde, por qué canal se avisa a un observador, qué modelo responde—. Lo que
sí se arregla es el disfraz: el comentario dice ahora lo que pasa, y el código
separa `ImportError` («no está escrito») del fallo de la llamada, para que el día
que se implementen un error suyo se vea en vez de confundirse con «no
disponible».

### El detector estuvo mal dos veces antes de servir, y esa es la lección

- **Primera versión:** comparaba los nombres importados contra las clases que
  cada módulo declara, sacadas por AST. Dio **412 «fallos»**, entre ellos `Money`
  y `Rate` — que obviamente existen, porque la aplicación arranca. Publicar esa
  cifra habría sido publicar basura.
- **Segunda versión:** `hasattr(modulo, nombre)`. Da falsos positivos con
  **submódulos**: `from app.services import dev_plan_service` funciona aunque
  `hasattr` sea falso hasta que alguien lo importe. Contó **8 roturas donde había
  3**.
- **La que sirve:** `tests/test_importes_diferidos.py` **ejecuta el import**. Es
  la única comprobación que no se puede equivocar sobre si un import funciona.

El fichero lleva además cuatro tests sobre el propio detector —uno con una rotura
plantada, otro con el falso positivo del submódulo— porque un estructural cuyo
detector está roto da luz verde sin mirar. Y la lista de los tres no
implementados **caduca sola**: si alguien escribe una, su test falla y obliga a
sacarla, que es cuando el estructural empieza a vigilarla. Sin eso, la lista de
excepciones se convierte en el sitio donde se esconden los importes rotos nuevos.

---

## 3.e Dieciocho ajustes que el código lee y la configuración no declaraba

Mismo método que la sección 3.d, otra pregunta: **¿hay algún
`getattr(settings, "X", defecto)` sobre un ajuste que no está declarado?** Uno
así devuelve **siempre** el defecto: la perilla no se puede tocar ni por `.env`
ni por variable de entorno, y quien la busque en la configuración no la
encuentra. Salieron **18**.

### Dos no eran perillas ausentes: eran nombres equivocados con el correcto al lado

| Leía | Existe | Consecuencia |
|---|---|---|
| `SMTP_PASSWORD` | **`SMTP_PASS`** | `smtp_pass` era siempre `None`, el `if smtp_user and smtp_pass` siempre falso, y **`server.login()` no se llamaba nunca**: *todos* los correos de notificación de la plataforma salían **sin autenticar**. Contra cualquier servidor que exija autenticación —prácticamente todos— se rechazan y el aviso no llega |
| `EMAILS_FROM_EMAIL` | **`SMTP_FROM`** | el remitente configurado se ignoraba y se caía a `noreply@…` |

Estaba en **dos** módulos: `notification_service.py:89` —el servicio general de
avisos, el que usa además el motor de automatizaciones— y
`bi_report_delivery_service.py:456`.

**Lo que lo delata:** en `notification_service.send_email`, la línea de arriba
lee **bien** `SMTP_FROM` y la de abajo **mal** `SMTP_PASSWORD`. La misma función
acierta un nombre y falla el otro. Y el defecto del remitente era además de otro
producto: `noreply@nexuspm.local`.

### Once declaradas, con el valor exacto que ya tenían

| Ajuste | Estaba fijo en | Por qué importa que se pueda tocar |
|---|---|---|
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | `None` | **el envío de SMS no se podía configurar de ninguna manera** |
| `CLIENT_TOKEN_EXPIRE_HOURS`, `PORTAL_SHARE_LINK_EXPIRE_HOURS` | 72 h | caducidades de **seguridad**, sin forma de bajarlas |
| `PBKDF2_ITERATIONS` | 260 000 | parámetro de seguridad que hay que poder **subir** con el tiempo sin tocar código |
| `AI_REVENUE_HOURLY_RATE_FALLBACK` | 85,0 | una tarifa **de negocio** escrita en duro |
| `WEBHOOK_CB_THRESHOLD` | 5 | umbral del cortacircuitos de webhooks |
| `MAX_APPS_PER_USER` | 10 | cuota del portal de desarrollador |
| `UPLOAD_DIR` | `uploads` | directorio de subidas |
| `JWT_ALGORITHM` | HS256 | correcto con clave simétrica; se declara para que esté en un solo sitio |

Cada una lleva **exactamente el valor que devolvía su `getattr`**, comprobado una
a una, así que declararlas **no cambia ningún comportamiento** — lo que cambia es
que ahora existen. Están en `app/core/config.py` **y** en `.env.example`, cada
una con su sección y el motivo escrito, y cero claves duplicadas (comprobado).

`UPLOAD_DIR` tenía además `getattr(settings, …) or os.environ.get("UPLOAD_DIR", "uploads")`:
**dos fuentes para el mismo ajuste**. Ahora pydantic lee el entorno por su cuenta
y la lectura es una.

### Cinco eran ramas muertas, y se quitan en vez de crear la perilla

En `db/seed_parts/core.py`: `NUMBERING_SEQUENCES`, `TASK_TYPES`,
`ALERT_CONFIGS`, `VACATION_USERS` y `CLIENTS_DATA` se leían con
`settings.X if hasattr(settings, "X") else [...]`. Son **datos de demostración**,
no configuración: declarar un ajuste para ellos sería peor que tenerlos en el
seed. Retirada la rama, que nunca se tomaba.

### El guardián

`tests/test_ajustes_declarados.py`, **26 tests**. El estructural exige que todo
ajuste leído con `getattr`/`hasattr` esté declarado; el resto fija los dos
nombres malos —para que no vuelvan— y los once defectos, para que cambiar uno
sea una decisión y no un efecto colateral de haberlos movido.

Y el test de «ahora se pueden configurar» **pone la variable de entorno de
verdad** y reconstruye `Settings`. Mi primera versión tenía un
`assert … or True`: pasaba siempre, o sea que no probaba nada. Un test que no
puede fallar es peor que no tener test, porque ocupa el sitio de uno que sí.

---

## 3.f El frontend llamando a rutas que no existen — y por qué el número engaña

La pregunta espejo de la 3.d: en vez de «¿el backend importa algo que no
existe?», **«¿el frontend llama a rutas que no existen?»**. Cada una es una
acción de la interfaz que devuelve 404.

**69 de 1.140** llamadas con ruta literal — el 6 %. **Y ese número, solo, es
engañoso.** Lo que importa es la clasificación:

| | Cuántas | Qué son |
|---|---|---|
| **No las alcanza ninguna pantalla** | **53** | código de cliente muerto: la ruta está mal pero nada la llama |
| **Alcanzables y sólo el prefijo o el nombre estaba mal** | **7** | **corregidas** |
| **Alcanzables y el endpoint NO existe** | **9** | trabajo de producto, listado abajo |

### Lo que me habría hecho publicar una falsedad

El primer instinto era reportar «69 acciones de la interfaz rotas». Habría sido
**falso**. El caso que lo destapó: `hooks/useAbsences.ts` define nueve hooks
—`useCreateAbsence`, `useApproveAbsence`, `useDeleteAbsence`…— que llaman a rutas
inexistentes, y **ninguno de los nueve lo usa ningún componente**. `AbsencesPage`
llama directamente a `absencesApi` con las variantes `*My`, que sí existen.

Así que hay que comprobar la **alcanzabilidad**: para cada llamada rota, ¿la usa
un `.tsx`, directamente o a través de un hook que un `.tsx` use? Sin ese paso, el
recuento mide código, no producto.

### Las siete corregidas

| Pantalla | Qué no funcionaba | Arreglo |
|---|---|---|
| `WikiPage` | **toda** la gestión de etiquetas | las cuatro operaciones existen bajo `/cmdb/wiki-tags/`; el cliente llamaba sin el prefijo |
| `EpicsPage` | el roadmap | `/roadmap` → `/epics/roadmap` |
| `EntitySelect` | el selector de subcontratistas | `/subcontractors` → `/enterprise/subcontractors` |
| `ITSMKnowledgeTab` | promover a error conocido | `promote-known-error` → `promote-kedb` |

**Y es la misma forma que los dos generadores de facturas del hallazgo 34: el
miembro correcto convivía con el roto.** `epicsApi.roadmap` apuntaba a `/roadmap`
y `epicsApi.roadmapByProject`, **la línea siguiente**, a `/epics/roadmap`. Hay
dos clientes de subcontratistas en el mismo fichero, uno con el prefijo bueno y
otro sin él. En las ausencias, `create`/`createMy`, `update`/`updateMy`,
`delete`/`deleteMy`: el bueno al lado del roto, siempre.

### Los nueve que NO se tocan, y por qué

No son ruta equivocada: **el endpoint no existe**. Comprobado ruta por ruta
contra el router real.

| Pantalla | Acción | Estado del backend |
|---|---|---|
| `ITSMKnowledgeTab` | `DELETE /sd/problems/{id}` | hay GET, PATCH y POST; **no hay DELETE** |
| `ITSMKnowledgeTab` | `GET /sd/known-errors/{id}/tickets` | no existe |
| `EnterprisePage` | `DELETE /oauth-integrations/{id}` | hay GET y POST; **no hay DELETE** |
| `TrainingPage` | `PATCH` y `DELETE /training/certifications/{id}` | sólo hay `GET` y `POST`: se puede crear una certificación y **no editarla ni borrarla** |
| `ExportsPage` | `POST /integrations/export/imputations` y `/projects` | los exports reales son `GET /analytics/exports/imputations-csv` y `resources-csv` — otro verbo, otra ruta, y «projects» no es «resources» |
| `usePipeline` | `GET /pipeline/{id}` | no existe |
| `ProjectsPage` | `GET /dependencies/{projectId}` | hay `/epic-dependencies/{project_id}` y `/task-dependencies/{…}`: **ambiguo cuál quiere la interfaz** |

Implementarlos o decidir a qué ruta apuntan son **decisiones de producto**, y
corregir la ruta a ciegas podría cambiar un 404 por un error de renderizado si la
respuesta tiene otra forma. Con 89 tests de frontend y ninguno sobre estas
pantallas, no tengo manera de distinguir una cosa de la otra sin abrir la
interfaz.

### El guardián

`tests/test_rutas_del_frontend.py` fija la cifra en **62** y usa
`route.matches(scope)` —el emparejador de Starlette— en vez de comparar formas a
mano: mis dos detectores anteriores de esta auditoría estuvieron mal por eso.
Lleva dos autocontroles, uno con una ruta que sí existe y otro con una inventada.

Y tiene un test que **obliga a bajar la constante** cuando se corrigen rutas: de
hecho es lo que pasó al arreglar las siete —el test se puso en rojo diciendo «hay
62 y la constante dice 69»—. Sin él, la constante se queda alta para siempre y
permitiría reintroducir lo ya arreglado.

---

## 3.g Ocho rutas inalcanzables porque otra las tapaba

En FastAPI **gana la primera ruta que encaja**. Si `/tasks/{task_id}` se declara
antes que `/tasks/dependencies`, la petición al segundo acaba en el manejador del
detalle con `task_id="dependencies"`. Y lo peor no es el fallo, es el mensaje:

```
GET /api/v1/tasks/dependencies        ->  404 {"detail":"Tarea no encontrada"}
GET /api/v1/sd/changes/rollout-plans  ->  404 {"detail":"Change request no encontrado"}
```

Quien depura eso **busca una tarea o un CR que falta**. Nadie mira el orden de
declaración de las rutas, porque nada apunta hacia ahí. Los tres devuelven ahora
**200**, comprobado llamándolos.

### Tres formas del mismo problema

| Forma | Dónde | Arreglo |
|---|---|---|
| Orden **dentro del fichero** | `tasks.py`: el bloque de dependencias iba tras `/{task_id}` | movido delante, verbatim |
| Orden **dentro del fichero** | `change_rollout.py`: las dos rutas de compatibilidad iban tras `/changes/{cr_id}/rollout-plans` | movidas delante |
| **Router registrado DOS VECES** | `issue_types` se incluía sin prefijo **y** con prefijo `/issue-types` | retirado el duplicado |
| Orden **ENTRE módulos** | `misc` se incluía antes de `change_rollout` y declara `/changes/{change_id}` | `change_rollout` movido delante en el `__init__` de service_desk |

**El registro duplicado merece detalle.** `issue_types.router` estaba incluido
dos veces, así que:

- cada ruta del fichero existía **duplicada**;
- las rutas ya empiezan por `/issue-types`, de modo que el registro con prefijo
  producía el absurdo `/api/v1/issue-types/issue-types/{project_id}`;
- y `/api/v1/issue-types/{project_id}` —del registro sin prefijo, que va
  primero— **tapaba seis rutas** del registro con prefijo.

Retirado el duplicado, la aplicación pasa de **2.046 a 2.033 rutas**: trece eran
copias. Se comprobó antes que el frontend usa las rutas **sin** prefijo y que
nadie llama a las dobles.

### El que más importaba no daba 404, daba 200 con menos datos

`/activity/project/{project_id}` estaba tapada por
`/activity/{entity_type}/{entity_id}` con `entity_type="project"` — y **los dos
manejadores no son equivalentes**:

- el genérico devuelve los eventos de **una entidad** (`activity_feed_payload`,
  límite ≤ 200);
- el tapado devuelve el feed **agregado**: eventos del proyecto **más todas sus
  tareas** (`project_activity_payload`, límite ≤ 500).

Así que el feed de actividad de un proyecto **salía sin las tareas**, con un 200 y
sin ningún error. Un 404 se acaba viendo; esto no.

### La regla, y el guardián

**Los segmentos literales se declaran antes que los `{parámetro}` de la misma
posición.** `tests/test_rutas_tapadas.py` la impone con
`route.matches(scope)` —el emparejador de Starlette, no una comparación de formas
a mano— y añade un test que prohíbe registrar un router dos veces. Lleva dos
autocontroles con aplicaciones de juguete: una con el orden malo, para comprobar
que lo ve, y otra con el bueno, para comprobar que no da falso positivo.

### Un test mío retirado por ser ruido

Escribí un tercer test que prohibía los caminos con segmento repetido
(`/sd/sd/…`, `/pipeline/pipeline`). Marcó **32**, y **todos funcionan**: son URLs
feas e inconsistentes, no un defecto, y arreglarlas sería cambiar URLs públicas —
romper a cualquier cliente que las use.

Un test que bloquea por algo que no está roto **es ruido, y el ruido es lo que
hace que se dejen de mirar los fallos**. Convertido en medición con la cifra
fijada en 32, porque ese patrón sí es la huella de la duplicación que dejó seis
rutas inalcanzables: si sube, conviene mirar si hay otro `include_router`
duplicado.

---

## 3.h El método que encontró casi todo, y qué preguntar la próxima vez

Las secciones 3.d a 3.g salieron todas de lo mismo, y **no de leer código**: de
formular una pregunta comprobable sobre una clase entera y dejar que una máquina
la contestara. Vale más que cualquiera de los hallazgos, así que queda escrito
con las preguntas ya hechas y las que quedan.

### Las seis preguntas y lo que dio cada una

| Pregunta | Resultado |
|---|---|
| ¿Hay `import` **dentro de una función** que apunte a algo que no existe? | **12 defectos** (§3.d) |
| ¿Hay `getattr(settings, "X", …)` sobre un ajuste **no declarado**? | **18**, incluidos dos nombres equivocados que dejaban todos los correos sin autenticar (§3.e) |
| ¿Llama el frontend a rutas que el backend **no atiende**? | 69, de las que **16 alcanzables** y 7 corregidas (§3.f) |
| ¿Hay rutas que otra declarada antes **intercepta**? | **8 inalcanzables**, una devolviendo 200 con menos datos (§3.g) |
| ¿Hay `db.commit()` cuyo fallo alguien atrape y **nadie deshaga**? | **5 arreglados**, 13 medidos y clasificados (§3.a del #22) |
| ¿Hay tareas periódicas definidas que **nada programe**? | **nada** — 30 de 32 en el `beat_schedule` y las otras 2 disparadas por código; ninguna entrada apunta a una tarea inexistente |

El último es un resultado negativo y **se anota igual**: alguien que retome esto
no tiene que volver a mirarlo.

### Las tres reglas que hacen que un detector sirva

Aprendidas cometiéndolas. **Mis detectores estuvieron mal cuatro veces** en esta
auditoría, y cada vez habría publicado una cifra falsa:

1. **Ejecuta, no razones.** El detector de importes comparó primero clases por
   AST (**412 «fallos»**, entre ellos `Money` y `Rate`, que obviamente existen) y
   luego con `hasattr` (**8 roturas donde había 3**, porque los submódulos
   importan aunque `hasattr` diga que no). El que sirve **ejecuta el import**. El
   de rutas usa `route.matches(scope)`, el emparejador de Starlette, en vez de
   comparar formas a mano.
2. **Prueba el detector en las dos direcciones.** Un caso plantado, para que lo
   encuentre, y un falso positivo conocido, para que no lo cuente. Un
   estructural cuyo detector está roto **da luz verde sin mirar**, que es peor
   que no tenerlo.
3. **Mide el producto, no el código.** El recuento del frontend eran 69, y 53 de
   ellas vivían en código que ninguna pantalla alcanza. Publicar «69 pantallas
   rotas» habría sido falso; lo cierto eran 16. **Sin el paso de
   alcanzabilidad, el número mide líneas y no usuarios.**

Y una cuarta sobre qué convertir en test: **un test que bloquea por algo que no
está roto es ruido**, y el ruido es lo que hace que se dejen de mirar los fallos.
El de caminos con segmento repetido marcaba 32 URLs feas pero funcionales: se
quedó como medición con la cifra fijada, no como puerta.

### Preguntas que no he hecho y parecen prometedoras

- ¿Hay **response_model** declarados que no correspondan a lo que devuelve el
  endpoint? FastAPI valida, así que fallaría en tests — probablemente poco
  fruto, pero no comprobado.
- ¿Hay **columnas de modelo** que ninguna consulta lee ni ningún esquema expone?
  Serían campos escritos y nunca usados.
- ¿Hay **permisos o roles** declarados en el catálogo GRC que ningún endpoint
  exija? Es la misma forma que el #27, ya cerrado, pero por el otro lado.
- ¿Hay **claves de i18n** que ningún componente use? Hay gate de cobertura al
  100 %, pero no de claves sobrantes.

---

## 4. Estado detallado de lo que sigue abierto

### #14 zonas horarias — **cerrado**, con una decisión que hay que respetar

Arquitectura, en `app/core/timeutil.py` y `app/core/timezone_context.py`:

- **Dos cadenas de resolución**, distintas a propósito porque responden a
  preguntas distintas:
  - `usuario → organización → UTC` para «qué día es hoy para esta persona»;
  - `cliente → organización → UTC` para los cortes de facturación (una factura
    tiene un periodo único, no uno por empleado).
- `clients.timezone` nuevo (revisión `090`), `NULL` = heredar de la organización.
- Cortes semiabiertos `[inicio, fin)`. El día del cambio de hora tiene 23 o 25
  horas, no 24.
- Los 169 `date.today()` de `services/`, `api/` y `core/` pasan por
  `timeutil.today()`, que lee la zona de un `ContextVar` publicado una vez por
  petición.

> **`bind_request_timezone` DEBE seguir siendo `async def`.** FastAPI ejecuta las
> dependencias síncronas en un hilo del threadpool y un `ContextVar` fijado ahí
> se pierde al volver. En versión `def` no publicaría nada, `today()` seguiría
> dando el día del servidor y **todo parecería correcto**. Medido con las cinco
> combinaciones; `tests/test_timezone_context.py` las fija.

> **No hay migración de desplazamiento del histórico, y es deliberado.** Se
> comprobó antes de tocar nada: de las escrituras a columnas de fecha-hora, 139
> usan `utcnow()`, 374 `datetime.now(timezone.utc)` y 437 `func.now()` — los
> datos almacenados **ya son UTC**. Aplicarles un «hora local → UTC» movería
> miles de instantes correctos por el offset del servidor y corrompería el
> histórico de forma irreversible. Los 27 `date.today()` de `db/seed_parts/` se
> dejaron a propósito: generan datos de demostración fuera de cualquier petición.

**Cerrado por completo, corrigiendo un consejo mío que era erróneo.** Este
documento decía que faltaba enganchar `period_bounds_for_client` en los cierres
de `billing_reports_service`. **Eso estaba mal**, y se comprobó columna por
columna: los cortes de facturación operan sobre columnas `Date`
—`Invoice.issue_date`, `period_from`, `period_to`, `Imputation.date`—, que son
días de calendario **sin instante**. No tienen zona que aplicar y su `extract`
ya era correcto; meter ahí un ayudante de límites *datetime* habría introducido
un error donde no había ninguno.

Lo que sí estaba mal eran **tres métricas mensuales** que agrupaban con
`extract("month", …)` sobre columnas de fecha-**hora** que guardan UTC:

| Columna | Métrica | Fichero |
|---|---|---|
| `SLABreachLog.breached_at` | incumplimientos de SLA por mes | `metrics/invoices_alerts.py` |
| `ClientNPS.created_at` | NPS medio por mes | `metrics/okr_nps.py` |
| `Task.completed_at` | tareas completadas por mes | `metrics/sprints_tasks.py` |

Agrupaban por el mes en que la fila está *almacenada*, no por el mes en que
ocurrió: una incidencia de las 22:30 UTC del 31 de julio se contaba en julio
cuando para Madrid era ya agosto. Corregidas con un agrupador compartido
(`app/services/metrics/_monthly.py`) que trabaja en la zona del contexto.
`timeutil` tiene ahora `month_key_in` y `month_label_in`. 16 tests en
`tests/test_monthly_metrics_timezone.py`, con contra-test que verifica que las
columnas `Date` siguen siendo `Date`.

> **Por qué se agrupa en Python y no en SQL:** `AT TIME ZONE` existe en
> PostgreSQL pero no en SQLite, así que esa cláusula rompería desarrollo y los
> tests. Esa divergencia entre motores es justo lo que causó el hallazgo 11.
> Son series de 12 a 24 puntos: el coste es irrelevante.

### #16 traducción — parcial, y el resto es trabajo de contenido

Hecho:
- Retirados fr, de, pt, it, pl. Quedan **es, en, zh** (los que se venden). El
  chino estaba en el catálogo con `enabled: false`.
- `UserProfilePanel` pintaba **su propia lista de 8 idiomas escrita a mano**,
  independiente del registro: ahora lee `AVAILABLE_LANGUAGES`. Era una segunda
  fuente de verdad.
- Gate **bloqueante** de cobertura (`frontend/scripts/check_i18n_coverage.mjs`)
  con el suelo en el valor medido: sólo puede subir.

**Pendiente, sin adornos:**
- Inglés y chino al **62,2 %**: faltan **1.419 claves en cada uno**, 2.838
  cadenas. Es contenido, no código. La terminología financiera y de PSA en chino
  hay que generarla en **lotes revisables**; no se debe declarar hecho de una
  pasada.
- ~1.100 literales castellanos incrustados en el JSX de `frontend/src/pages/`.
- Medir con `node frontend/scripts/i18n_gap.mjs --keys en` para el listado
  exacto de claves que faltan.
- **Al traducir, subir `COBERTURA_MINIMA` en `check_i18n_coverage.mjs`.**

### #18 complejidad — parcial, con dos defectos reales encontrados de paso

**La métrica honesta.** El *recuento* de funciones sobre el umbral se mueve
poco (138 → 94), porque partir una función grande produce varias medianas. La
que importa es el **exceso total sobre 10: 1.023 → 247 (−76 %)**, y el **máximo,
que era 247 y ahora es 16**.

Medido con:

```bash
PY=./.venv/Scripts/python.exe
$PY -m ruff check app --extend-select C901 --output-format concise \
  | grep -oE 'complex \([0-9]+' | grep -oE '[0-9]+' \
  | $PY -c "import sys; v=[int(x) for x in sys.stdin]; print(\"funciones %d exceso %d maximo %d\" % (len(v), sum(x-10 for x in v), max(v)))"
```

Lo cerrado hasta ahora, por tandas:

| Función | Antes | Ahora | Verificación |
|---|---|---|---|
| `_fetch_metric_series` (`bi_smart_alerts/metrics.py`) | **247** en 945 líneas | resuelto por tabla | 133 series a JSON, idénticas |
| `validate_graph` (`workflow_designer_service.py`) | 42 | bajo umbral | 38 grafos, salidas idénticas |
| `collaboration_ws` (`endpoints/collaboration/ws.py`) | 39 | bajo umbral | **23 tests nuevos** (tenía cero) |
| `execute_actions` (`automations_service.py`) | 38 | 13 | 37 tests existentes |
| `apply_routing_rules` (`routing_rule_service.py`) | 35 | bajo umbral | 62 casos + **59 tests nuevos** (tenía cero) |
| `build_tenant_context` (`ai_chat/context_service.py`) | 34 en 525 líneas | bajo umbral | 36 claves byte-idénticas + **14 tests nuevos** |
| `sso_callback` (`api/v1/routers/auth_sso.py`) | 32 | bajo umbral | tests PKCE/nonce + 1 nuevo de regresión |
| `apply_ticket_update` (`ticket_update_service.py`) | 29 | bajo umbral | 23 casos con reloj fijo + **26 tests nuevos** |
| `lifespan` (`app/main.py`) | 29 en 216 líneas | bajo umbral | **43 tests nuevos** (tenía cero) |
| `evaluate_condition` (`services/abac.py`) | 26 | bajo umbral | 289 combinaciones + **35 tests nuevos** |
| `_serie_cost_profile` (`bi_smart_alerts/metrics.py`) | 27 | bajo umbral | **18 tests nuevos**, valores a mano |
| `_serie_invoice` (idem) | 24 | bajo umbral | **14 tests nuevos**, valores a mano |
| `calc_project_profitability` (`profitability_service.py`) | 23 | bajo umbral | **26 tests nuevos** (tenía cero de valor) |
| `validate_and_create_imputation` (`imputation_service.py`) | 20 | bajo umbral | 4 existentes + **4 tests de orden** |
| `_serie_tickets_open` (`bi_smart_alerts/metrics.py`) | 18 | bajo umbral | **20 tests nuevos**, valores a mano |
| `login` (`api/v1/routers/auth_core.py`) | 18 | bajo umbral | 39 de auth + **3 nuevos de seguridad** |
| `_serie_pending_timesheets` (idem) | 13 | bajo umbral | catálogo + equivalencia 133 claves |
| `update_user_record` (`services/user_service.py`) | 23 | bajo umbral | **15 tests nuevos**; ver 3.b |
| `_rotate_integration_secrets` (`services/key_management.py`) | 21 | bajo umbral | **9 tests nuevos** (tenía cero); ver 3.b |
| `_check_auto_approval` (`approval_engine/requests.py`) | 18 | bajo umbral | **24 tests nuevos** (tenía cero); ver 3.b |
| `request_logger` (`app/main.py`) | 11 | bajo umbral | **incluido en los 43 de `main.py`** |
| `seed` (`db/seed_parts/core.py`) | **67** | bajo umbral | 22 fases con nombre + **17 tests nuevos** |
| `_execute_node` (`service_desk/workflow_engine.py`) | 22 | bajo umbral | **46 tests nuevos**; 2 defectos, ver 3.c |
| `_notify_recipients` (`collaboration/messages.py`) | 22 | bajo umbral | **68 tests nuevos** |
| `call_ai` (`ai_provider_service.py`) | 24 | bajo umbral | **18 tests nuevos**; atribución del proveedor corregida |
| `discover_snmp_network` (`cmdb/discovery.py`) | 21 | bajo umbral | **37 tests nuevos**; dos copias de 100 líneas unificadas |
| `predict_overrun_ml` (`ai_modules/predictions.py`) | 19 | bajo umbral | **equivalencia por fuerza bruta: 192.000 combinaciones** + 36 tests |
| `create_campaign` (`performance_service.py`) | 18 | bajo umbral | suite completa |
| `evaluate_alerts` (`bi_smart_alerts_service.py`) | 17 | bajo umbral | suite completa |
| `_suggest` (`semantic_classifier.py`) | 17 | bajo umbral | **57 tests nuevos**, cargas calculadas a mano |
| `update_scim_user` (`scim_service.py`) | 16 | bajo umbral | **36 tests nuevos**; asimetría PUT/PATCH fijada |
| `generate_invoice_pdf` (`invoice_pdf.py`) | 16 | bajo umbral | **35 tests nuevos**; defecto NOSPLIT, ver 3.c |
| `search` + `_apply_filters` (`collaboration/_search.py`) | 16 | bajo umbral | suite de búsqueda |
| `apply_filter` (`report_builder_service.py`) | 15 | bajo umbral | **62 tests nuevos**; 2 defectos, mutación ×2 |

**Trece de ellas no tenían un solo test** antes de tocarlas, y en cada caso eso
era un hallazgo por sí mismo. Los cuatro peores:

- **`lifespan`** — 216 líneas que son el *arranque* de la aplicación, sin una
  sola prueba propia. Incluye la comprobación de deriva de esquema y el arranque
  del planificador.
- **`calc_project_profitability`** — 38 cifras de dinero (P&L y EVM completos de
  un proyecto) y la cobertura que había era de endpoint: códigos de estado, ni
  una cifra comprobada.
- **`request_logger`** — se ejecuta en *cada* petición y tapa los secretos de la
  URL antes de loguearla. Que tape de verdad no estaba verificado, y `login`
  responde 4xx con `?code=...` en la URL.
- **`_check_auto_approval`** — decide si una solicitud se aprueba **sin revisión
  humana**. Buscando `auto_approval`, `_check_auto_approval` o `auto_approve` en
  todo `tests/` no aparecía nada. Ver la sección 3.b.

#### Dos defectos reales encontrados al escribir los tests

Ninguno de los dos se buscaba; los dos son el patrón central de la auditoría
(sección 5): **no fallaban, devolvían cero**.

**1. Facturas sin fecha de vencimiento, invisibles a las siete métricas de
facturación.** La consulta compartida de `_serie_invoice` filtraba
`Invoice.due_date >= start_date`. `due_date` es *nullable* en el modelo y
opcional en la API (`InvoiceCreate.due_date: Optional[date] = None`), y en SQL
`NULL >= fecha` no es ni verdadero ni falso: la fila se descartaba. Una factura
sin vencimiento no aparecía en **ninguna** de las siete, incluidas las cuatro
que van por fecha de emisión o de pago y no necesitan el vencimiento para nada
—borradores, enviadas, cobradas e importe cobrado—.

Corregido con `or_(due_date >= start, due_date.is_(None))`, que sólo *añade* las
filas que sobraban; el filtro de fecha propio de cada métrica sigue descartando
las que no tienen mes al que ir. Fijado por
`test_bi_invoice_metrics.test_una_factura_sin_vencimiento_no_desaparece`, que
falla contra el código anterior — es su razón de ser.

**2. `cost_profile_total_annual` devolvía `int 0`.** `round(sum([]), 2)` es `0`,
no `0.0`, así que sobre una organización sin perfiles de coste era la única
métrica del catálogo con tipo mixto en la serie. Menor, pero lo cazó el test y
está corregido.

#### Un docstring mío que era falso, corregido

Al extraer `_arrancar_planificador` escribí que devuelve `None` cuando manda
Celery beat. **No es verdad**: levanta el planificador igualmente. Lo que impide
llegar ahí es `_enforce_scheduler_mode_safety()`, que corre antes y **aborta el
arranque en modo dual en todos los entornos por defecto** (`FAIL_ON_DUAL_SCHEDULER`
a 1). El producto estaba bien; el docstring atribuía la guarda a la función
equivocada. Está corregido y hay tres tests que fijan la guarda de verdad.

Lo apunto porque es la clase de error que un test que sólo lee el código no
caza: mi test falló al *ejecutar* la función, y por eso se descubrió.

#### El método, que conviene repetir

**Extracción verbatim con un script, no reescritura a mano.** El script mueve
cada rama con su condición, su cuerpo y sus comentarios, y `compile()` antes de
escribir. Sobre eso, tres capas de verificación según lo que esté en juego:

1. **Valores calculados a mano** cuando la función devuelve cifras (métricas de
   coste, de facturación, de tickets, P&L). No capturados del código: si el
   código y la aritmética discrepan, discrepan de la aritmética. Así se
   encontraron los dos defectos de arriba.
2. **Identidades de la especificación** para lo derivado. En el P&L los
   indicadores EVM se comprueban contra sus definiciones estándar
   (CPI = EV/AC, EAC = AC + (BAC−EV)/CPI, ETC = EAC−AC, VAC = BAC−EAC, CV = EV−AC,
   SV = EV−PV) a partir de PV, EV y AC ya fijados a mano. No es tautología: caza
   un intercambio de operandos, que es el error probable al mover ese código.
3. **Comparación contra la versión anterior** cuando hay muchas salidas. Para
   `metrics.py` hay una foto del fichero pre-refactor en
   `tests/_fixtures/metrics_pre_refactor.py` y
   `tests/test_bi_metrics_equivalencia.py` compara las **133** claves del
   catálogo sobre los mismos datos, con dos diferencias declaradas (las dos
   correcciones de arriba) y un test que exige que esas diferencias *ocurran*,
   para que la lista de excepciones no pueda tapar una regresión.

**No actualices esa foto.** Si se actualiza con el código nuevo, la comparación
se hace contra sí misma. Hay un test (`test_la_foto_previa_es_la_de_verdad`) que
lo comprueba precisamente porque es el fallo más fácil de cometer ahí.

**Y una decisión que hay que revisar, dicha en voz alta:** esa foto son **81 kB
de código duplicado y congelado** en el repositorio. Se ha dejado porque el test
de equivalencia es lo único que comprueba las **133 métricas por valor** y no
sólo por estructura, y porque su cabecera y su test guardián dejan su estado sin
ambigüedad — no es código que *parezca* vivo, que es lo que la auditoría
penalizaba en el hallazgo de código muerto.

Pero es deuda, y tiene fecha de caducidad natural: `metrics.py` ya está **entero
bajo umbral**, así que no queda ningún refactor pendiente ahí que necesite esa
red. **La recomendación es borrar la foto y su test** (`tests/_fixtures/` y
`tests/test_bi_metrics_equivalencia.py`) en cuanto se dé por bueno este commit;
lo que se mantiene son los tests por métrica con valores a mano
(`test_bi_cost_profile_metrics`, `test_bi_invoice_metrics`,
`test_bi_ticket_metrics`), que son los que fijan las cifras y no dependen de
ninguna copia.

#### Propiedades que ahora están fijadas y antes no

Un refactor podía romper cualquiera de éstas sin que nada más fallara:

- **El 401 de `login` es idéntico** para «usuario inexistente» y «contraseña
  incorrecta». Los dos caminos están ahora en la misma función
  (`_rechazar_credenciales`) para que no puedan divergir por descuido: si
  divergieran, el login sería un oráculo de usuarios existentes.
- **El orden de las nueve reglas de `validate_and_create_imputation`.** Decide
  qué error ve la persona cuando incumple dos a la vez. El tope de 24 h gana al
  duplicado, y eso importa: el 409 de duplicado es recuperable con
  `force_duplicate`, así que si ganara, se podría forzar y colar un día de 26 h.
- **«Abierto» y «resuelto» usan listas de estados distintas.** Un ticket
  cancelado no está abierto pero tampoco cuenta como resuelto. Uniformarlas por
  descuido cambiaría las dos métricas a la vez.
- **Las tres medias de tickets promedian sobre las filas que tienen el dato**, no
  sobre todos los tickets del mes. Dividir entre todos hundiría el CSAT de
  cualquier mes con tickets sin encuestar.
- **Media frente a suma en las agrupaciones de coste.** `dept_max_per_hour` y
  `country_max_per_hour` son el máximo de las *medias* del grupo;
  `top_country_annual` es el máximo de las *sumas*. No es un descuido y ahora
  está escrito.
- **La tabla de pesos de progreso cubre los siete `TaskStatus`.** Un estado nuevo
  no puede entrar valiendo cero sin que alguien lo decida.

#### Séptima instancia del patrón, retirada

`hasattr(project, "tasks")` en `calc_project_profitability`. `tasks` es una
relación declarada del modelo, así que la comprobación siempre era verdadera:
defensa muerta que sólo servía para ocultar el día que dejara de serlo.

**Lo que queda.** 94 funciones entre 11 y 16, y aquí hay que ser preciso porque
la primera versión de este párrafo decía algo que no había comprobado.

**Medido** sobre las ocho más grandes que quedan, contando la cadena `if/elif`
más larga de cada una con un script AST:

| Función | Líneas | `elif` seguidos | Comparaciones `==`/`in` | |
|---|---|---|---|---|
| `apply_filter` (`report_builder_service.py`) | 30 | **12** | 13 | ← **hecha**, traía 2 defectos |
| `materialize_recurring_tasks_cmd` | 74 | 4 | 8 |
| `stop_timer_session` | 132 | 0 | 13 |
| `evaluate` (`ai_governance.py`) | 103 | 0 | 10 |
| `run_agent_stream` | 195 | 0 | 6 |
| `critical_path_payload` | 87 | 0 | 5 |
| `_project_internal_cost` | 88 | 0 | 3 |
| `ws_doc_collab` | 111 | 0 | 4 |

La conclusión que sale de la tabla, y no de la intuición: **de las ocho, sólo una
ocultaba una tabla de despacho**. `apply_filter` eran 12 `elif` sobre el mismo
`operator` en 30 líneas —el caso más limpio que quedaba en el repo— y traía
**dos** defectos (los dos apartados siguientes). **Ya está hecha.** Las otras
siete son largas por otra razón: corrutinas anidadas, bucles sobre grafos,
cálculo. Partirlas mejora el número y poco más.

**Recomendación, por tanto: el #18 está en el punto de parar.** Lo que quedaba
con valor real era `apply_filter`, y está cerrado. Para las 96 restantes —todas
entre 11 y 16— **no montes una tanda dedicada**: pártelas cuando haya que tocar
el fichero por otra razón. Entre 11 y 16 el rendimiento decreciente es real, y
esto sí está medido, no supuesto.

Si aun así se quiere seguir, el orden por tamaño es `ws_doc_collab` (16),
`run_agent_stream` (16), `critical_path_payload` (16),
`materialize_recurring_tasks_cmd` (16) y `_project_internal_cost` (16). Y hay un
apunte de duplicación que sale de este mismo fichero y vale más que cualquiera de
ellas: **`execute_report` y `execute_report_paginated` son la misma función.**
Medido con `difflib` sobre sus cuerpos, ignorando sangría: **41 de 50 líneas
idénticas, el 82 %**. Lo único que cambia es la firma y el bloque final —una
devuelve una lista con `limit`, la otra un diccionario con `paginate_query`—; el
acotado por tenant, la validación de columnas, el bucle de filtros y el orden son
copia exacta. Las dos se quedaron en complejidad 11 después de sacarles
`apply_filter`.

Unificarlas baja el exceso en 2 y, más importante, **quita la posibilidad de que
una arregle un fallo y la otra no** — que no es hipotético: es exactamente lo que
pasó con PUT y PATCH en SCIM (§ del #18) y con las dos copias del sondeo SNMP. De
todo lo que queda en el #18, esto es lo que más vale por hora.

### El defecto de `apply_filter`: un filtro `in` que no filtra

`operator: "in"` con un valor que **no es una lista** cae en

```python
elif operator == "in":
    if isinstance(value, list):
        query = query.filter(col.in_(value))
```

y **devuelve la consulta sin filtrar**, es decir *todas* las filas. Pasa las dos
validaciones del llamador —`op in OPERATORS` y `col_name in allowed_cols`, que
sí están y sí devuelven 400— porque el que falla es el **tipo del valor**, y
`value` está declarado `Any` sin validación de esquema.

Efecto: quien construye un informe «estado está en [...]» y cuyo cliente manda
una cadena en vez de una lista **no recibe un error: recibe el informe completo**
con todas las filas, y las cifras son plausibles. No es fuga entre clientes —el
filtro de tenant es aparte y es *fail-closed*—, pero sí «el filtro que pediste no
se aplicó y nadie te lo dijo». Undécima instancia del patrón de la sección 5.

**Resuelto**, y la invariante que lo fija está escrita en el módulo: **ningún
operador de la tabla puede dejar la consulta sin filtrar.** Cada entrada devuelve
una cláusula, siempre. Un escalar en un `in` se interpreta como lista de un
elemento —que es lo que la persona quería decir— pero nunca como «no filtres
nada». `col.in_([])` y `col.in_([None])` devuelven **cero** filas, que es lo
correcto para «está en el conjunto vacío»; devolverlas todas no lo era para nada.

El otro camino de «filtro que no filtra» de la misma función —
`if not hasattr(model, column): return query`, con una columna del catálogo que
no existe en el modelo— **era inalcanzable y ahora además lanza**. Es un 500 y no
un 400 a propósito: una incoherencia entre catálogo y modelo es un error del
servidor, no de quien pide el informe, y un 500 se ve en los logs mientras que un
informe con filas de más no se ve en ningún sitio. Que siga siendo inalcanzable
lo sostiene un test estructural que cruza las **243 columnas** de `ENTITIES` con
sus modelos.

Y los 12 operadores de `apply_filter` se cruzan con las 12 claves de `OPERATORS`
en otro test: si divergen, un operador que la validación acepta y la tabla no
implementa volvería al mismo fallo por la otra puerta.

**Verificado por mutación,** que es lo único que demuestra que un test sirve:
reintroducido el comportamiento antiguo del `in`, **15 tests caen**, incluido el
de extremo a extremo por el endpoint. Restaurado, todos en verde.

### Y el hallazgo que salió de escribir ese test: la entidad «Riesgos» no existe

`get_model_class()` resuelve 16 entidades opcionales con

```python
("app.models.resources", "Risk", "risks"),
```

y **`Risk` no está en `app.models.resources`: está en `app.models.pipeline`.**
El `getattr(mod, class_name, None)` devuelve `None`, el `except (ImportError,
AttributeError): pass` no se entera, y `get_model_class("risks")` devuelve
`None` — así que `execute_report("risks", …)` responde
`400 Entidad 'risks' no soportada en este entorno`, **siempre, en todos los
entornos**.

Mientras tanto `ENTITIES["risks"]` declara **16 columnas** con sus etiquetas y
su grupo (`proyectos_recursos`), así que **la interfaz ofrece «Riesgos» como
entidad reportable** y quien la elige recibe un 400 que dice «no soportada en
este entorno», que suena a configuración y no a error de código.

**Duodécima instancia del patrón,** y de las más limpias: catálogo completo,
pantalla, y una ruta de módulo equivocada tapada por un acceso tolerante.

**Resuelto con una línea** —`app.models.pipeline`— y comprobado antes de tocar
nada que basta: las 16 columnas del catálogo existen en `Risk`.

**Lo que había que verificar de verdad, porque el arreglo ACTIVA una ruta que
estaba muerta:** que el acotado por tenant la cubra. Lo hace por dos vías
independientes, y las dos están comprobadas — `Risk` tiene `organization_id`, así
que entra por la primera rama del acotado de `execute_report`; y por debajo está
el listener `do_orm_execute` de `app/db/session.py`, que es *fail-closed*. Se
comprobó además que **las 20 entidades del catálogo tienen `organization_id`**,
así que ninguna cae en la rama sin acotar. Habilitar una entidad reportable sin
esa comprobación habría sido cambiar un 400 por una fuga.

**Verificado por mutación:** devuelta la ruta a `app.models.resources`, caen 4
tests y uno reproduce el mensaje original —
`{"detail":"Entidad 'risks' no soportada en este entorno"}`—. Restaurado, verde.

`tests/test_report_filters.py`, **62 tests**, incluye el estructural que cruza
las 20 entidades con sus modelos: es el que impide que vuelva a pasar con otra
entidad, que es lo que importa más que el arreglo de ésta.

**La conclusión del hallazgo, que vale más que el número:** partir una función
compleja es en sí mismo un método de detección. **Dieciocho defectos reales**
en 47 funciones, tres de ellos de seguridad, y ninguno se estaba buscando. La
lista completa, para que el número sea comprobable y no una afirmación:

| # | Defecto | Dónde salió |
|---|---|---|
| 1 | Las siete métricas de facturación perdían la factura sin vencimiento | `_fetch_metric_series` (247) |
| 2 | `cost_profile_total_annual` devolvía `int 0` en vez de `0.0` | `_serie_cost_profile` (27) |
| 3 | Autoedición de campos reservados por un no-admin *(seguridad)* | `update_user_record` (23) |
| 4 | La rotación cifraba el criptograma de un secreto ilegible *(seguridad)* | `_rotate_integration_secrets` (21) |
| 5 | `PATCH /users/{id}` saltaba las validaciones de manager *(seguridad)* | idem |
| 6 | El nodo «crear ticket» no podía funcionar nunca (`description` NOT NULL) | `_execute_node` (22) |
| 7 | `except` sin `rollback()`: el fallo de un nodo tumbaba todo lo siguiente | idem |
| 8 | El tipo de nodo `action` se guarda y no tiene ejecutor | idem |
| 9 | Una factura de 29 líneas o más no se generaba (`NOSPLIT`) | `generate_invoice_pdf` (16) |
| 10 | `call_ai` registraba el uso contra el proveedor equivocado al repliegue | `call_ai` (24) |
| 11 | `apply_filter`: un `in` con valor no-lista devuelve todo sin filtrar | comprobar una afirmación mía |
| 12 | La entidad «Riesgos» del constructor de informes devuelve 400 siempre | escribir el test del 11 |
| 13 | El job de auto-resolución: `commit()` sin `rollback()` deja el panel en «running» y tapa el error real | detector de `commit()` sin deshacer |
| 14 | El guardia `already_running` sólo cubría el camino asíncrono: dos pasadas síncronas podían solaparse y resolver el mismo ticket dos veces | la asimetría del 13 |
| 15 | La cola de flujos abortaba **entera** y el elemento quedaba en `processing` para siempre, sin barrido que lo rescate | idem, dentro de un bucle |
| 16 | El bucle de respaldo de IA descartaba una respuesta **ya facturada** y envenenaba la sesión para todos los proveedores siguientes | idem |
| 17 | El camino primario de IA marcaba `status = "error"` en un proveedor que **había funcionado** | idem |
| 18 | Una subida de adjunto correcta se convertía en un 500 por el `commit()` best-effort del índice de texto | idem |

Los dos últimos salieron de otra manera que los diez anteriores y merece
decirse. **El 11, de comprobar una frase que yo había escrito sin medirla:**
había afirmado que a las 97 restantes «no les quedan tablas de despacho», y al
medirlo con un script AST resultó que a una sí, y que traía defecto. **Y el 12,
de escribir el test estructural del 11:** al cruzar las 243 columnas del
catálogo de informes con sus modelos, una entidad entera no resolvía su clase.
Escribir una afirmación comprobable y luego comprobarla es un método de
detección, y escribir el test que la sostiene es otro.

Ninguno se habría encontrado leyendo el código: la asimetría entre dos copias de
cien líneas sólo se ve cuando están una al lado de la otra, y un `elif`
inalcanzable sólo se ve cuando se pregunta qué tiene que pasar para llegar ahí.

### #19 gráficos — cerrado, con el diagnóstico corregido

**El diagnóstico original de la auditoría estaba equivocado.** Decía «elegir una
librería y migrar». El troceo por vendor *ya estaba bien hecho* —plotly, echarts,
recharts y d3 tenían cada uno su chunk en `vite.config.ts`—, así que el problema
no era cuántas librerías hay sino **quién las importa**.

Lo que de verdad pasaba, medido sobre el grafo del build:

```
route-misc importaba ESTÁTICAMENTE  →  vendor-plotly  (4.634 kB, 38 % de todo el JS)
                                    →  vendor-d3      (130 kB)
```

Causa: `src/pages/CMDBPage.tsx` importaba `CMDBTopologyGraph` y `Cmdb3dGraph` de
forma estática. Consecuencia: abrir **cualquiera** de las páginas del chunk
`route-misc` descargaba plotly entero, incluidas las que no muestran ni una
gráfica.

Arreglado con dos `lazy(() => import(...))` y un límite de `Suspense` — el mismo
patrón que `charts/DynamicChart` ya usaba para las otras cuatro gráficas de
plotly. **Medido antes y después:**

| | Antes | Después |
|---|---|---|
| Abrir una página de `route-misc` | 7.382 kB | **2.385 kB** (−68 %) |
| Tamaño del chunk `route-misc` | 2.749 kB | 2.385 kB |
| JS total | 12,0 MB | 11,7 MB |

**Gate nuevo:** `frontend/scripts/check_heavy_chunks.mjs`, bloqueante en
`ci_local.sh`. Ninguna ruta puede depender estáticamente de un vendor de más de
400 kB. Necesita un build previo, así que se salta si no existe `dist/`.

> La primera versión del gate llevaba una lista de librerías «pesadas» escrita a
> mano e incluía `recharts`. **Eso era un error**: recharts (304 kB) es la
> librería principal, usada en 18 sitios, y diferirla pondría un indicador de
> carga en cada panel. El criterio es el **tamaño**, que no hay que mantener a
> mano. Verificado que el gate se pone rojo inyectando la regresión en el
> `dist`, no sólo que pasa en verde.

**Lo que NO se ha hecho**, y era el consejo original: consolidar las cuatro
librerías en una. Con el coste de carga ya resuelto, migrar 25 usos de echarts y
18 de recharts es riesgo alto y beneficio ahora marginal. Queda como deuda
medida, no forzada. `echarts` 5→6 sigue siendo uno de los saltos mayores
pendientes.

### #22 organización de módulos — parcial

**Era peor de lo que decía mi propia auditoría.** No eran «Organizations y
Slack»: `mfa_service.py` tenía **ocho dominios sin relación** en 1.435 líneas
—MFA, organizaciones, Slack, presupuestos, planificación asistida, escenarios,
PDF y tokens de BI— y el router `app/api/v1/endpoints/mfa.py` tiene el mismo
problema: **38 rutas** de esos ocho dominios en un fichero llamado «mfa».

Hecho: repartido en ocho módulos de servicio. `mfa_service.py` pasa de 1.435 a
**170 líneas** y contiene sólo MFA.

```
app/services/mfa_service.py            170  (sólo MFA)
app/services/organizations_service.py  181
app/services/slack_service.py          185
app/services/budgets_service.py        133
app/services/ai_planning_service.py    288
app/services/scenarios_service.py      182
app/services/pdf_export_service.py     224
app/services/bi_tokens_service.py      162
```

Se comprobó por AST **antes** de partir que no había ni una llamada entre grupos
ni un solo ciclo: los ocho dominios nunca estuvieron acoplados, sólo apilados,
así que el reparto fue mecánico y los cuerpos se movieron verbatim. El diff del
router es *exclusivamente* imports y llamadas — ni una ruta tocada, verificado
sobre el propio diff. **103 imports muertos** cayeron solos al separarlos.

> Aviso de una trampa en la que caí: el script de reparto lee `mfa_service.py` y
> escribe los ocho módulos, **incluido `mfa_service.py`**. Ejecutarlo dos veces
> vacía los otros siete, porque la segunda pasada lee el fichero ya reducido a
> MFA. Si hay que volver a lanzarlo, restaurar primero el original.

**El router también, repartido.** Las 38 rutas de `endpoints/mfa.py` pasan a
ocho ficheros, cada uno con su etiqueta propia en la documentación de la API
(antes las 38 colgaban de un solo tag «MFA & Budgets»):

```
endpoints/mfa.py            5 rutas · 1 modelo
endpoints/organizations.py  6 rutas · 2 modelos
endpoints/slack.py          5 rutas · 1 modelo
endpoints/budgets.py        5 rutas · 2 modelos
endpoints/ai_planning.py    4 rutas
endpoints/scenarios.py      5 rutas · 1 modelo
endpoints/pdf_export.py     2 rutas
endpoints/bi_tokens.py      6 rutas · 1 modelo   (+ el ayudante get_bi_token)
```

Registrados en `app/api/v1/routers/delivery.py`. **Verificado que las 2.051
rutas de la aplicación son idénticas antes y después: ninguna perdida, ninguna
nueva.** Eso era lo crítico, porque **ABAC y GRC derivan el módulo de permisos
de la propia ruta**, así que un path alterado cambiaría los permisos en silencio.
187 tests de los ocho dominios más ABAC y GRC pasan.

Los modelos Pydantic intercalados se asignaron al dominio de la primera ruta que
los sigue. `get_bi_token` no tiene decorador de ruta, así que hubo que asignarlo
a mano (el script aborta si aparece otro caso así, en vez de dejarlo caer).

**Los módulos `v2xx`, fuera — y había un tercer caso del mismo patrón.**

`v238_service.py` eran 784 líneas con **seis dominios** dentro. Repartido igual
que `mfa_service` (cero llamadas entre grupos, cero ciclos, comprobado por AST):

```
app/services/pipeline_stages_service.py     etapas del embudo comercial
app/services/capacity_planning_service.py   conflictos de reserva, nivelado Gantt
app/services/adhoc_analytics_service.py     consultas ad-hoc, drilldown, cross-filter
app/services/payments_service.py            enlaces de pago, webhook de Stripe
app/services/collab_snapshots_service.py    instantáneas de edición colaborativa
app/services/scim_service.py                (+ scim_bulk_error, ver aviso abajo)
```

Y el directorio `app/api/v1/endpoints/v239/` desaparece: sus tres ficheros ya
estaban bien nombrados —`approval_builder`, `baselines`, `branding`—, lo que
agrupaba por versión era la carpeta. Verificado que las 2.051 rutas siguen
idénticas.

> **Corrección a una afirmación mía demasiado amplia.** Escribí «ya no queda
> ningún módulo nombrado por número de versión», y en el mensaje del commit
> `0804bfc` también. Es cierto en las capas de **servicio y API** —de lo que iba
> este hallazgo— pero no en todo el árbol. Quedan:
>
> ```
> app/db/seed_parts/v10.py  v12.py  v13.py     datos de demostración
> tests/test_business_logic_v236.py  v238.py  v239.py
> tests/test_v235_features.py  test_v236_features.py
> ```
>
> **No los he renombrado, y el motivo es el daño real del hallazgo:** el CRUD de
> organizaciones estaba escondido en el módulo de MFA y por eso nadie vio que le
> faltaba su guarda de superadministrador. Ese riesgo aplica a código de producto
> con controles de acceso, no a generadores de datos de demostración ni a tests.
> Renombrarlos es barato pero no reduce riesgo. Si se hace, los seeds son
> multi-dominio («Sprints, Expenses, Automations» en uno solo), así que
> renombrarlos bien exige partirlos primero.

**Dos `hasattr` más eliminados de paso.** `analytics_extended.py` tenía
`if hasattr(v238_service, "run_analytics_drilldown")` y otro igual para el
filtrado cruzado: **el mismo patrón que dejó muerto `/analytics/adhoc`**. Con el
módulo repartido habrían empezado a devolver 200 con filas vacías sin un error en
los registros.

> **Error mío en este bloque, y la comprobación que lo evita.** El generador creó
> un `app/services/scim_service.py` y **sobrescribió uno que ya existía con 509
> líneas**, dejándolo en 32. Se detectó porque la app dejó de importar
> (`cannot import name 'ensure_org'`), se restauró de git, y el script comprueba
> ahora colisiones **antes** de escribir. Al generar módulos nuevos: verificar
> siempre que el nombre está libre.
>
> `scim_bulk_error` sí tocaba moverla, y está en el `scim_service` real. Tiene
> **cero llamantes** en todo el repositorio — comprobado. Se conserva porque el
> aprovisionamiento SCIM en bloque es funcionalidad declarada, pero documentada
> como lo que es.

**Pendiente, y es lo único que mantiene esta fila en «parcial»:** los
`db.query()` y `db.commit()` de la capa API — los puntos donde un endpoint
habla con la base sin pasar por un servicio.

> **Corrección del recuento.** Aquí decía «298 puntos en 44 ficheros». La cifra
> real al empezar el trabajo era **299**: mi propio arreglo del rollback en
> `ai_auto_resolution` había añadido un `db.commit()` después de la medición
> original. Y a mitad de camino cité «200 restantes», que también estaba mal:
> la medición era **204**. Las dos veces el error fue mío al arrastrar cifras en
> vez de volver a medir. **Estado medido hoy: 204 puntos en 35 ficheros.** Moverlos
es trabajo grande y de riesgo real sobre código en producción: hacerlo **por
dominios, no de golpe**, cada tanda con su suite.

**Medido, porque el reparto no es plano y eso cambia el plan.** Dos dominios se
llevan **dos tercios**:

| # | Dominio | Puntos | Acumulado | Peor fichero |
|---|---|---|---|---|
| 1 | `collaboration` | **127** | 43 % | `workspaces.py` con **52** |
| 2 | `service_desk` | **74** | 67 % | `workflow_designer.py` con 14 |
| 3 | `collaboration_portal` | 19 | 74 % | (un solo fichero) |
| 4 | `performance` | 15 | 79 % | (un solo fichero) |
| 5 | `jira_integration` | 12 | 83 % | (un solo fichero) |
| 6 | `user_costs` | 10 | 86 % | (un solo fichero) |
| 7 | `baselines` | 9 | 89 % | (un solo fichero) |
| 8 | `branding` | 7 | 92 % | (un solo fichero) |

Las 16 restantes suman 25 puntos entre todas, con 1-3 cada una: **no merecen
tanda**. El plan que sale de la tabla es `collaboration` primero —y dentro de
ella `workspaces.py`, que sola es el 17 % del total—, después `service_desk`, y
parar en el octavo dominio: ahí ya está el 92 %.

#### Tanda 1 cerrada: `collaboration`, de 127 puntos a 0

Ocho ficheros de endpoint, ocho módulos de servicio. El recuento de rutas de
cada fichero se comparó **uno a uno contra HEAD** antes y después: 35, 12, 8,
11, 4, 16, 9 y 5 — idénticos. Ninguna ruta añadida, ninguna perdida.

| Fichero de endpoint | Puntos | Servicio | Líneas |
|---|---|---|---|
| `workspaces.py` | 52 | `services/collaboration/workspaces.py` | 483 → 1301 |
| `compliance.py` | 18 | `compliance.py` (nuevo) | 321 → 154 el endpoint |
| `calls.py` | 18 | `calls.py` (nuevo) | 248 → 106 el endpoint |
| `bots.py` | 11 | `webhooks.py` (nuevo) | — |
| `files.py` | 11 | `files.py` (nuevo) | — |
| `messages.py` | 9 | ampliado | — |
| `admin.py` | 8 | `admin.py` (nuevo) | 210 → 134 el endpoint |
| `tus.py` | 1 | `tus.py` (nuevo) | — |

#### Cómo se verificó, porque un recuento de decoradores no prueba nada

La primera versión de esta sección decía «ninguna ruta perdida» contando
decoradores `@router.`. **Eso no prueba que las rutas sean las mismas**, así que
se comprobó de verdad, con un `git worktree` en HEAD y dos procesos separados
—dos versiones del paquete `app` no se pueden importar en el mismo intérprete—:

| Comprobación | Resultado |
|---|---|
| Conjunto de `(método, ruta)` de toda la aplicación | **2.029 en HEAD, 2.029 ahora, conjuntos idénticos**: 0 perdidas, 0 nuevas |
| OpenAPI de las 1.574 rutas, campo a campo | idéntico salvo **`description` en 7 rutas** (docstrings). Ni un cambio en `parameters`, `requestBody`, `responses`, esquemas o seguridad |
| Acceso directo a base en los endpoints, **por AST** y no por `grep` | **0**, mirando llamadas a los 19 métodos de sesión sobre cualquier receptor |

**Y el AST destapó algo que el `grep` no vio**: `ws.py` —que no estaba entre los
ocho ficheros porque ya tenía cero puntos— **crea su propia sesión** con
`SessionLocal()`. Ver más abajo.

#### El hueco de mi propia verificación, y cómo se cerró

Cruzando las rutas de colaboración con los tests salió que **20 no las menciona
ninguno**, y nueve estaban en ficheros que este refactor reescribió: `presence`,
`presence/me`, `mentions`, `retention/settings` (GET y PUT), `push/subscribe`,
`push/unsubscribe`, `bots/invoke` y `rotation-status`.

Los tests que había escrito cubren los **servicios**. El cableado del endpoint no
lo cubría nada, y el cableado es justo lo que rompe un refactor: un argumento en
otro orden, un `await` que falta, un modelo de respuesta que ya no encaja.

`tests/test_collaboration_endpoints_cableado.py` (12 tests) los ejercita por
HTTP. **Y encontró un fallo en el acto**: yo había escrito el test suponiendo que
los ajustes de retención tenían una clave `retention_months`, y son
`default_months` y `max_months`. Suponer la forma de la respuesta era
exactamente el error que este test existe para cazar.

**Lo importante no es el recuento: es que mover el acceso a base funciona como
detector.** Sacar las consultas del endpoint obliga a nombrar qué devuelve cada
operación, y ahí se ve lo que dentro de un bucle de construcción de respuesta no
se veía. Lo que apareció:

1. **El legal hold no retenía lo que decía retener** — dos defectos en la misma
   función y en direcciones opuestas: un caso con custodia sólo de cliente o de
   canal no protegía nada (destrucción de material bajo retención legal), y un
   caso que no nombraba a nadie paralizaba la retención entera. Ninguno daba
   error. Fijado en `tests/test_legal_hold_retencion.py` (14 tests).
2. **El plazo de las URL firmadas estaba en duro a 3600 s en cuatro sitios**,
   ignorando `S3_URL_EXPIRATION_HOURS`, que es configurable en caliente por
   organización.
3. **TUS era una puerta trasera a la validación de subidas**: tope propio de
   500 MB —cinco veces `MAX_FILE_SIZE_MB`— y **cero validación de contenido**,
   mientras `/attachments`, que escribe en la misma tabla y el mismo almacén,
   comprueba extensión, MIME declarado, bytes mágicos y su coherencia. Bastaba
   subir por TUS para colar lo que la otra puerta rechaza. Además duplicaba la
   materialización del adjunto; ahora las dos vías pasan por
   `files.crear_adjunto`.
4. **`days` del calendario se declaraba y no se usaba.** Y sin límite inferior,
   `orderBy=startTime` devolvía los eventos **más antiguos** del calendario
   presentándolos como «próximos». En M365 se pasó a `calendarView`, que es el
   recurso con ventana temporal: `events` con `$filter` habría devuelto la serie
   maestra de una reunión periódica con su fecha original.
5. **Una integración con el token caducado seguía anunciándose como conectada**
   y aportaba cero eventos, sin log: el bucle tenía un `except: continue` mudo y
   los clientes devuelven `{"error": ...}` en vez de lanzar.
6. **El alta de suscripción Web Push podía dar un 500.** `endpoint` es único
   global; la consulta quedaba acotada al tenant, así que el mismo navegador
   usado luego por alguien de otra organización no encontraba su fila y chocaba
   contra la restricción única. Es un caso real —una suscripción Web Push
   pertenece al registro del service worker, no a la sesión—, así que la fila se
   traspasa y el traspaso se audita **en las dos organizaciones**: la que pierde
   las notificaciones tiene que poder verlo en su propia auditoría.
7. **7 patrones N+1** escondidos en bucles de construcción de respuesta.
8. **Dos fuentes de verdad para los slash commands** —la tabla de ejecutores y
   una lista de ayuda escrita a mano— unificadas en una sola.
9. **Contenido remoto sin escapar en HTML**: el callback de OAuth interpolaba
   `r.text[:200]` de la respuesta del proveedor en un `<pre>`.
10. **Cuatro límites operativos en duro** ahora son ajustes declarados, y el
    idioma de la transcripción sale de `DEFAULT_LANGUAGE`.
11. **El WebSocket del chat corría con el aislamiento por organización
    apagado.** Su sesión es un `SessionLocal()` creado a mano y `info` estaba
    vacío durante toda la conexión: con `is_superadmin` ausente, las **tres**
    capas se saltan por la rama de «sesión no inicializada (job de fondo /
    test)» —`TenantSession.query()`, `TenantSession.execute()` y el escuchador
    `do_orm_execute`—. El contexto se pone ahora en cuanto se resuelve el
    usuario, y no antes: `get_active_user_by_id` busca por id sin saber todavía
    de qué organización es, así que ésa tiene que correr sin filtrar.
12. **Un evento «está escribiendo» se podía inyectar en la conversación de otra
    organización.** El `conversation_id` llegaba del cliente y no se comprobaba:
    se publicaba en `conv_channel(cid)` fuera cual fuera. No leía nada —la
    suscripción sí está acotada por pertenencia y organización, comprobado— pero
    escribía en un canal ajeno a nombre del usuario. Ahora se exige que el canal
    esté entre los que esta conexión tiene suscritos, que es la lista que el
    servidor ya calcula.

Los dos últimos vienen de `ws.py`, que **no estaba en los ocho ficheros de la
tanda**: tenía cero puntos de acceso directo, así que el hallazgo 22 no lo
señalaba. Apareció al cambiar el `grep` por un análisis AST para comprobar mi
propia afirmación de «cero accesos». Es la tercera vez en esta auditoría que la
verificación de una afirmación mía destapa un defecto que no se estaba
buscando.

Y **un defecto mío**, corregido en el mismo trabajo: audité el traspaso de la
suscripción push **después** del `db.commit()`. `_audit.write` sólo hace `add` y
deja la confirmación a quien llama, así que esos registros no se guardaban. Un
solo `commit` al final, y el cambio queda atómico.

---

#### Tanda 2, en marcha: `service_desk`, y lo que había en la auto-resolución de IA

**El dominio mide 89 puntos, no los 74 de la tabla de arriba**: esa cifra es
anterior a cambios posteriores y se corrige aquí. Y ya tiene ~30 módulos de
servicio, así que casi todo es ampliar y no crear.

El primer fichero, `ai_auto_resolution.py` (17 puntos), tenía **cuatro defectos
de la misma familia: algo que debería ser por cliente y no lo era.**

1. **El trabajo procesaba tickets de TODAS las organizaciones.**
   `run_daily_auto_resolution_job` acepta `organization_id` y su propio docstring
   dice que sin él «procesa todos». El endpoint **no lo pasaba**, y en el camino
   asíncrono la sesión es un `SessionLocal()` recién creado —sin contexto de
   tenant—, así que el filtro se salta por diseño. Un administrador de un cliente
   lanzaba la auto-resolución sobre los tickets de **todos los demás**,
   resolviéndolos y comentándolos. **No es una lectura cruzada: es una escritura
   cruzada**, y es el defecto más serio de esta tanda.
2. **La configuración era global.** Clave de `AppSetting` sin organización: los
   umbrales de confianza, el auto-cierre y el tope del trabajo los cambiaba
   cualquier administrador **para todos los clientes**. Y el comentario de
   cabecera del propio servicio ya decía que esa config es «por organización»:
   la intención estaba escrita y el código no la cumplía.
3. **El estado y el historial del trabajo eran globales**: un cliente veía el
   `job_id`, las marcas de tiempo, las estadísticas y los errores de otro.
4. **El cerrojo era uno para todo el proceso.** `_AUTO_RES_JOB_LOCK = Lock()` a
   nivel de módulo: con el trabajo de un cliente en marcha, el de otro recibía
   `already_running`. Sigue siendo un cerrojo en proceso —no coordina entre
   varios workers de Uvicorn, y eso queda dicho en su docstring—, pero ya no
   bloquea a los demás clientes.

**El módulo ya tenía la convención buena y sólo para una cosa.** El contador de
feedback se arregló en su día a `feedback_stats::{org}`, con un comentario que
explica que antes «stats de orgs distintas se mezclaban y el composite_confidence
usaba historical rate cross-tenant». La config, el estado y el historial se
quedaron fuera. Se sigue esa misma convención en vez de inventar otra, con una
regla por dato: **la config hereda de la clave global** —es el valor por defecto
del despliegue y una organización que no ha tocado nada debe usarlo—, **el estado
del trabajo no** —el trabajo de otro no es el suyo—.

> **Y un error mío en el primer intento, que cazó el test:** guardaba con la
> clave heredada cuando no había organización y leía de `::global`. Guardar en
> una clave y leer de otra. Ahora la misma función resuelve las dos.

**Un comentario obsoleto que había hecho el filtro peor.** El acotado por
organización del trabajo era un `outerjoin` a `Project` con esto al lado:
«FIX: Ticket no tiene organization_id propia; scope vía Project». **Sí la
tiene** —comprobado en el modelo—, y el filtro que implementaba dejaba pasar los
tickets **sin proyecto a todas las organizaciones** por su
`or_(project_id IS NULL, ...)`. Es además la columna que usa la propia guarda de
tenant de `TenantSession`, así que filtrar por otra vía era incoherente. Ahora es
`Ticket.organization_id == organization_id`.

> Yo también me fié de ese comentario: dije que `Ticket` no tenía la columna
> antes de mirarlo. Un comentario no es una comprobación.

Fijado en `tests/test_auto_resolution_por_tenant.py` (7 tests, los siete en rojo
antes del arreglo). Los dos dobles de `run_daily_auto_resolution_job` que ya
existían en la suite se actualizaron a la firma nueva, y el del camino sincrono
**comprueba ahora que llega la organización de quien llama**, que es la pregunta
que estaba sin hacer.

**Lo que queda de este fichero:** nueve `commit()`/`rollback()` de frontera de
transacción. Bajarlos significa mover la **orquestación del trabajo** —cerrojo,
transiciones de estado, tarea de fondo y registro del fallo— a la capa de
servicio, con la disciplina de rollback que ya lleva documentada. Es un paso
aparte y se hace con su verificación, no de refilón.

#### `collaboration_portal`: el portal era una segunda vía de envío sin los controles de la primera

21 consultas y escrituras, **y ninguno de sus ocho endpoints lo tocaba un test**.
Su envío de mensajes reimplementaba una versión pobre del interno:

* **Reparto de notificaciones parcial, con una comparación imposible.** Sólo
  avisaba en conversaciones directas, sólo a los dos usuarios internos, y se
  protegía con `uid != current_client.id`. `user_a_id` y `user_b_id` son de
  `users`; `current_client.id` es de `client_users`. **Esa comparación nunca
  podía ser falsa**: ni filtraba al autor ni alcanzaba a los clientes. Los
  clientes contraparte no recibían nada, y en canales y grupos no se avisaba a
  nadie. El aparato interno ya sabía tratar destinatarios cliente y excluir al
  autor por `client_user_id` — hacía falta usarlo, no duplicarlo.
* **Sin escaneo DLP.** La vía interna sí lo aplica. Misma forma que las dos
  puertas de subida de adjuntos: mismo destino, una con controles y otra sin.
* **Sin indexado para búsqueda.** Ver el aviso de abajo sobre el alcance.
* **Sin hilos**: `parent_message_id` no creaba `CollaborationThread`.
* **El ancla de paginación se buscaba por id sin acotarla a la conversación**,
  así que un id de otra conversación desplazaba la ventana con una fecha ajena.
* **El tope de 25 mensajes por minuto, en duro.** Ahora
  `COLLAB_PORTAL_MESSAGE_PER_MIN`.
* **N+1 en el listado de conversaciones**: una consulta por conversación para
  averiguar su título. Ahora son tres, una por tipo.

El arreglo no reescribe nada de eso: llama a `messages.send_message` con
`client_user_id`, que pasa a ser **la única vía de envío**.

> **Corrección de mi propia lectura, y del primer test que escribí.** Documenté
> el indexado como «un cliente no encontraba sus propios mensajes», y **eso es
> falso en la configuración por defecto**: `SimpleSqlSearch.index()` —y el
> `PgFtsSearch` que hereda de él— son **no-op**, y su búsqueda consulta la tabla
> de mensajes, así que con SQLite o Postgres se encontraban igual. El indexado
> sólo hace algo con `COLLAB_SEARCH_BACKEND=opensearch`, y ahí sí eran
> invisibles. Peor: mi primer test comprobaba que la búsqueda encontraba el
> mensaje, y **pasaba también sin el arreglo** — no discriminaba nada. El de
> ahora espía la llamada al indexado, que es lo que de verdad cambió. Lo dejo
> escrito porque un test que pasa por la razón equivocada es peor que no tenerlo.

15 tests nuevos (`tests/test_collaboration_portal.py`) para ocho rutas que no
tenían ninguno.

#### Y lo que salió de medirlo: cinco `commit()` que dejaban la sesión abortada

Contar accesos no dice si hay defecto. La pregunta que sí lo dice —«¿hay algún
`db.commit()` cuyo fallo alguien atrape y **nadie deshaga**?»— destapa el mismo
defecto que apareció en el motor de flujos de trabajo: tras un `commit()`
fallido la sesión queda en **transacción abortada**, y todo lo que venga después
falla también, **incluido el registro del propio error**.

> **Antes de las cifras, una corrección.** La primera versión de mi detector iba
> **por bloque `try`** en vez de por llamada a `commit()`, y tenía dos falsos
> positivos: contaba un `try`/`finally` sin `except` —que no se traga nada— y no
> veía el `rollback` cuando estaba en un `try` anidado. Con él publiqué «3 en
> `app/api` y 19 en `app/services`». Reescrito **por llamada**, los números son
> los de abajo, y el detector tiene ahora cuatro tests que lo prueban en las dos
> direcciones: uno con un caso plantado (que lo encuentre) y tres con los falsos
> positivos (que no los cuente). Un detector que sobrecuenta se acaba ignorando;
> uno que subcuenta da luz verde.

**Medido bien:** en `app/api`, 8 `commit()` atrapados **con** `rollback`, 102 que
propagan al llamador —lo que no es este defecto— y los que estaban en riesgo,
**ya arreglados**. En `app/services`, 44 con `rollback`, 770 que propagan y
**13 en riesgo**.

**Los cinco arreglados,** y el discriminador de gravedad es si están dentro de un
bucle, porque ahí una sesión envenenada rompe *todas* las iteraciones siguientes:

| Sitio | Qué pasaba | En bucle |
|---|---|---|
| `ai_auto_resolution.py` (camino síncrono) | el `except` escribía el registro de fallo y hacía `commit()` sin deshacer: el registro no se escribía nunca, el panel se quedaba en «running» y el error real quedaba tapado por un `PendingRollbackError` | no |
| `bookings_service.py` (cola de flujos) | lo mismo **dentro del bucle de la cola**: el `commit()` del fallo reventaba, el `raise` abortaba la cola entera —los elementos siguientes no se procesaban— y el que falló se quedaba en `processing`, estado del que **no hay ningún barrido que rescate** (comprobado: `"processing"` sólo se escribe ahí y nadie lo consulta) | **sí** |
| `ai_provider_service.py` ×2 | el `commit()` de **estadísticas** estaba dentro del `try` de la llamada, así que un fallo de nuestra base descartaba una respuesta de IA **ya atendida y facturada**; en el bucle de respaldo envenenaba además la sesión, de modo que todos los proveedores siguientes fallaban y la función acababa diciendo «todos los proveedores han fallado» — el diagnóstico contrario al real. Y en el camino primario marcaba `status = "error"` en un proveedor que **había funcionado**, que es el valor que lo excluye de futuras selecciones | **sí** (uno) |
| `collaboration/files.py` | `commit()` best-effort del índice de texto; al fallar, la respuesta lee atributos de `att` que `expire_on_commit` (True por defecto) expiró, SQLAlchemy intenta refrescarlos y **una subida correcta se convierte en un 500** | no |
| `scim.py` | el `AuditLog` de un **borrado de usuario** se perdía y la sesión quedaba sucia. Que sea *best-effort* está declarado en el código, así que es decisión tomada — pero un borrado sin rastro merece saberse | no |

El arreglo de los dos de IA **no es meter un `rollback()`**: es separar «la
llamada al proveedor falló» de «nuestra contabilidad falló». Lo primero significa
probar el siguiente proveedor y marcar el que falló; lo segundo, no: la respuesta
se devuelve igual, el fallo se deshace y se registra.

**Honestidad sobre la autoría de los dos de IA:** esa forma **viene del
original**, comprobado en `git show cfce2a4~1`. Mi refactor de `call_ai` la movió
*verbatim* —que era el objetivo declarado del movimiento— y apareció después, al
pasarle el detector. Mover verbatim conserva los defectos: eso es lo que hace el
movimiento verificable, y es la razón de pasar detectores **después** en vez de
confiar en que partir una función los encuentre todos.

**Y el guardia que sólo protegía la mitad.** En el mismo `ai_auto_resolution.py`,
`_AUTO_RES_JOB_LOCK` se tomaba en la rama `run_async=True` y se liberaba en su
`finally`; la rama síncrona **no lo tomaba nunca**, así que dos llamadas con
`run_async=False` podían solaparse entre sí y con una asíncrona ya en cola — y el
trabajo resuelve tickets automáticamente, así que solapar dos pasadas puede
resolver el mismo ticket dos veces. Ahora el camino síncrono lo toma y lo libera
en un `finally`, con un test que comprueba que se libera **también cuando el
trabajo revienta**: sin `finally` se cambiaría un fallo puntual por una avería
permanente.

#### Los 8 que quedan, y los 2 que se dejan a propósito

De los 13 de `app/services`, **tres estaban dentro de un bucle** y dos ya están
(`bookings_service` y el de respaldo de IA). Los otros diez son fuera de bucle,
así que el fallo es local a su petición:

```
app/services/accounting_hub_service.py:46      app/services/cmdb/discovery.py:731
app/services/ai_modules/_base.py:128           app/services/collaboration/_thumbnails.py:112
app/services/approval_engine/_base.py:331      app/services/organizations_service.py:112
app/services/approval_engine/_base.py:355      app/services/pdf_export_service.py:202
app/services/approval_engine/requests.py:542   app/services/pdf_export_service.py:209
```

**Los dos que sí están en bucle y NO se han tocado** son
`app/services/collaboration/_scheduler.py:62` y `:70`, la entrega de mensajes
programados. Su defecto es real y tiene forma concreta: **si `_notify_recipients`
sale bien y el `commit()` del flag `_scheduled_delivered` falla, la notificación
ya se ha enviado y el flag no se ha guardado, así que el siguiente tic la vuelve
a enviar** — notificación duplicada. Además todo el bucle está dentro de un solo
`try`, así que un fallo pierde el tic completo.

**No se ha tocado, y es una decisión, no un olvido:** el arreglo correcto es un
`try` **por mensaje** alrededor de un cuerpo `async` que hace `await
bus.publish(...)`, es decir tocar la ruta de entrega en tiempo real. Eso merece
su propia tanda con su propia suite; meterlo de propina en una tanda que ya toca
seis ficheros es exactamente la chapuza que este trabajo intenta evitar. El
`finally: db.close()` que ya existe hace un `rollback` implícito, así que la
sesión no queda envenenada más allá del tic.

Hay un test que **fija el número en 13** (`tests/test_commit_rollback.py`): si
sube, alguien ha añadido uno nuevo y se entera al momento.

### #32 marca blanca — **cerrado**, los cinco generadores

`OrgBranding` define cinco colores y un nombre por organización y tiene pantalla
para configurarlos. Sólo lo leían su propio endpoint y el portal de cliente: los
cinco generadores que producen lo que ve el cliente final **no lo leían, y
ninguno recibía siquiera el `organization_id`**. Un cliente configuraba su
marca, la veía en la web, y sus facturas salían con los colores y el nombre de
Contecflow.

**Decisión tomada: el documento lleva la marca del tenant.**

#### El mapeo NO es uno a uno, y mapearlo así rompe el documento

| Campo de `OrgBranding` | Va a | Por qué |
|---|---|---|
| `primary_color` | banda de cabecera de tabla | es el color con el que el cliente se identifica |
| `accent_color` | acento | líneas, énfasis, filetes |
| `text_color` | texto **sobre** la banda | con guarda de contraste, ver abajo |
| `app_name` | nombre en la cabecera | antes salía el ajuste global `PROJECT_NAME` |
| `secondary_color` | **nada** | es un tono saturado; en un tinte de tabla deja los importes ilegibles |
| `text_color` → `texto_principal` | **nunca** | vale `#f8fafc` por defecto (claro, porque en la web va sobre fondo oscuro): sería **texto blanco sobre papel blanco**, una factura ilegible generada sin error |

Los tintes de tabla se quedan neutros a propósito: un tinte neutro funciona
debajo de cualquier tono de marca, uno saturado no funciona debajo de nada.

#### La legibilidad está demostrada, no ajustada a ojo

El contraste WCAG depende **sólo** de la luminancia relativa. Con blanco y negro
**puros** como candidatos, el peor caso está donde los dos empatan:

```
1,05 / (L + 0,05) = (L + 0,05) / 0,05
(L + 0,05)² = 0,0525   →   L = 0,1791
contraste = 1,05 / 0,2291 = 4,58
```

**4,58 > 4,5**, así que para *cualquier* color de marca hay siempre un texto
legible y **no hace falta tocarle el color al cliente**. Un test recorre los 256
grises para comprobarlo.

> **Corrección a mi propio diseño.** La primera versión llevaba maquinaria para
> oscurecer el color de marca hasta que admitiera texto legible, porque había
> derivado que existía una banda de tonos medios sin solución. **Era falso**: el
> error venía de usar `#111111` en vez de negro puro. Retirada la maquinaria.
>
> Y el detalle que sostiene la garantía queda fijado con números, porque
> «suavizar» el negro parece cosmético y la rompe: en **cinco fondos**, de
> `#777777` a `#7b7b7b`, el blanco y un `#111111` **fallan los dos** y sólo el
> negro puro cumple. Cinco tests, uno por fondo.

#### El logotipo NO se trae, y es deliberado

`OrgBranding.logo_url` es una URL que escribe el cliente. Descargarla al generar
el PDF sería una petición saliente a un destino que él controla —**SSRF**— y
metería su latencia y sus caídas en la ruta de emitir una factura. Traerlo bien
necesita lista blanca de destinos, tiempo de espera, caché y tamaño máximo: es
su propia pieza, no una línea aquí.

#### Los generadores: cuatro hechos, uno identificado y no hecho

`invoice_pdf`, `report_pdf`, `signature_pdf` y `campaign_pdf` aceptan `paleta` y
sus llamadores la resuelven con `marca_de_organizacion()`, que devuelve colores y
nombre **en una sola consulta**. Dos decisiones anotadas:

- en `campaign_pdf`, `WARNING` y `MUTED_BG` **no** se sustituyen: son colores de
  **estado** —aviso y «anonimizado»— y su significado no depende de la marca. Un
  aviso pintado con el color de marca deja de leerse como aviso;
- `SUCCESS` era una constante de módulo de `campaign_pdf` que **no usaba nadie**:
  código muerto, retirado en vez de trasladado.

**Los correos quedan fuera**, y es scope declarado: son plantillas HTML con CSS
en línea y el mecanismo es otro (los clientes de correo no soportan lo mismo que
ReportLab). Merece su pieza.

#### Corrección: había un SEXTO camino, y ya está hecho

Dije «los cinco generadores están cableados». **Incompleto.** Al comprobar por
barrido qué generadores de PDF alcanza la capa API apareció
`app/services/report_pdf_service.py::build_report_pdf`, que es el que produce los
**informes programados que se envían por correo** — es decir, otro documento que
llega al cliente final.

Dos cosas de él:

- **ya recibe `org_id`**, pero lo usa sólo para *traer los datos*, no para la
  marca. Así que cablearlo es baratísimo: el dato ya está en la firma;
- tiene **10 colores en duro repartidos por 14 ayudantes**, y son una **paleta
  distinta de las tres que la auditoría ya había encontrado** — `#4f8ef7`,
  `#1e293b`, `#22c55e`, `#ef4444`, `#f59e0b`—. O sea que el hallazgo de «seis
  colores de marca escritos 91 veces en 29 ficheros» tenía además una cuarta
  variante que no estaba contada.

Su rama `custom` cae a `report_pdf.generate_report_pdf`, que **ya acepta
paleta**, así que ese camino se arregla con un argumento. El resto —su propia
construcción de historia— necesita pasar la paleta por los 14 ayudantes.

**Hecho en la tanda siguiente.** Los tres colores de marca viajan dentro del
diccionario `styles`, que **todos** los ayudantes reciben ya, así que no hubo que
pasar la paleta por catorce firmas. `BG_DARK` quedó muerto al sustituirlo y se
retiró.

Los neutros y los de **estado** se quedan en el fichero, y por razones distintas:
sus grises difieren en un pelo de los de la paleta compartida (`#1e293b` frente a
`#1a1a2e`) y unificarlos cambiaría el aspecto de un documento que se manda al
cliente; y `SUCCESS`, `WARNING` y `DANGER` son estado, no marca — un aviso
pintado con el color de marca deja de leerse como aviso.

**Y de probar este generador salió el hallazgo de la sección 3.d:** en la salida
apareció `cannot import name 'Resource'`, que resultó ser el primero de doce
importes diferidos rotos.

#### Y un defecto que salió de leer el lector de marca que ya existía

`GET /orgs/{id}/branding` devolvía, para una organización sin marca configurada,
un diccionario de **literales escritos a mano** que duplicaba los `default=` del
modelo. Ya había divergido en dos sentidos:

- `app_name` devolvía **`"NexusPM"`** —un nombre de producto anterior, que sigue
  en los docstrings de `esign`, `jira` y `m365`— mientras el modelo declara
  `default="Contecflow"`. **Cualquier organización que no hubiera tocado su marca
  veía ese nombre en su interfaz**;
- faltaban `background_color` y `text_color`, o sea **2 de los 5 colores**, así
  que quien leía la API para una organización sin configurar recibía un payload
  incompleto.

Resuelto leyendo los `default=` declarados en el modelo
(`OrgBranding.__table__.columns[…].default.arg`), que es donde ya estaban.
`app_name` es la excepción deliberada: sale de `settings.PROJECT_NAME`, porque el
nombre por defecto es el de la **plataforma** y no un valor de marca del cliente.

Duplicar valores por defecto no es un problema de estilo: es garantizar que un
día divergen, y aquí ya lo habían hecho.

---

### Otros pendientes con riesgo propio

- `strictNullChecks` (226 errores) y `noImplicitAny` (387).
- `echarts` 5→6 y `react-router-dom` 6→7: son los **3 moderate** que quedan en
  `npm audit`. Cada uno es una migración con riesgo real sobre las 119 rutas
  lazy, así que están medidos y no forzados. El gate bloqueante está en nivel
  `high`, que está a 0.

---

## 5. Patrón que atraviesa toda la auditoría

Conviene tenerlo presente al seguir: el fallo dominante de este código **no** es
código ausente, es **controles escritos, con interfaz, con tests que pasan, y
conectados a nada**. Quince casos confirmados:

1. `ABACMiddleware` — nunca se ejecutó.
2. `ABAC_COVERED_PREFIXES` — 45 de 110 prefijos con cero llamadas a
   `enforce_abac`. Cobertura «aspiracional».
3. `/analytics/adhoc` — `hasattr` sobre una función inexistente, devolvía
   siempre `results: []`.
4. La matriz de permisos GRC — `check_permission()` con cero invocaciones; sólo
   su propia pantalla leía la tabla.
5. El reconocimiento ASC 606 de T&M — `getattr` a dos campos inexistentes,
   cero euros siempre.
6. Las **siete** métricas de facturación — filtro `due_date >= inicio` con
   `due_date` nullable: la factura sin vencimiento desaparecía de todas,
   incluidas las cuatro que van por emisión o por pago.
7. La rotación programada de secretos — un `elif` de respaldo que era
   inalcanzable para su propósito declarado y, para lo que sí alcanzaba,
   **cifraba el criptograma**.
8. `_check_auto_approval` — decide aprobaciones **sin revisión humana** y tenía
   cero tests.
9. `PATCH /users/{id}` — el endpoint dedicado de manager valida existencia,
   organización y ciclos; el genérico aplicaba `manager_id` con un `setattr` y
   ninguna de las tres.
10. El tipo de nodo `action` de los flujos de trabajo — pasa la validación del
   diseñador, se guarda y se dibuja, y **no tiene ejecutor**. El flujo se queda
   parado ahí sin decir por qué. Ver la sección 3.c.
11. `apply_filter` del constructor de informes — un filtro `in` cuyo valor no es
   una lista **no filtra**: devuelve todas las filas, sin error. Un filtro que
   no filtra es literalmente un control desconectado. Ver el apartado del #18.
12. La entidad «Riesgos» del constructor de informes — 16 columnas en el
   catálogo, visible en la interfaz, y la ruta del módulo apunta a
   `app.models.resources` cuando `Risk` está en `app.models.pipeline`. Todo
   informe sobre riesgos devuelve 400. Ver el apartado del #18.
13. **El generador bueno de facturas** — trazado completo, paginación, paleta y
   datos fiscales, detrás de una ruta que **no llamaba nadie**, mientras la
   interfaz usaba otro generador sin el NIF del cliente. Es la variante más
   costosa del patrón: no es que el control no hiciera nada, es que **lo hacía
   bien y en el sitio equivocado**, y todo el mantenimiento se invirtió ahí.

14. **Las notificaciones de Slack** — `get_slack_webhook_url` importaba
   `SlackConfig` de un modulo inexistente y un `except ImportError: return None`
   convertia el fallo en «no configurado». Con datos validos sembrados, no
   salieron nunca. Es la instancia mas pura del patron: el docstring explicaba
   el silencio como una decision del usuario. Ver la seccion 3.d.

15. **La autenticación SMTP de todos los correos** — el código leía
   `SMTP_PASSWORD` y el ajuste es `SMTP_PASS`, así que `server.login()` no se
   llamaba nunca. No es un control desconectado por un `getattr` tolerante sino
   por un **nombre equivocado con el correcto al lado**, y el efecto es el
   mismo: la credencial configurada no se usaba y nada lo decía. Ver 3.e.

Los quince comparten mecanismo: **un acceso tolerante (`getattr`/`hasattr` con
defecto, un `except` que degrada, o un filtro que descarta en silencio)
convirtiendo un error en un resultado plausible.** Al revisar código nuevo aquí,
ese es el patrón a buscar.

Y accesos tolerantes muertos retirados hasta ahora, que son la señal de aviso
del patrón: `hasattr` sobre `project.tasks`, sobre `payload.context`, y los dos
de `analytics_extended.py`. Los cuatro eran siempre verdaderos, así que la
defensa no defendía de nada — sólo escondía el día en que dejara de serlo.

---

## 5.b Los tres tests que estaban en rojo sin que nadie lo viera

Aparecieron al ejecutar por primera vez la suite completa **en paralelo**, y los
tres eran del mismo tipo: código de verificación que había dejado de verificar.

| Test | Causa | Arreglo |
|---|---|---|
| `test_i18n_complete::test_all_lang_files_exist` | `EXPECTED_LANGS` con los **ocho** códigos escritos a mano | Lee `APP_LANGUAGES` vía `tests/_i18n_langs.py` |
| `test_business_logic_v239::test_v239_section_exists_in_all_8_languages` | `_LANGS` con los ocho, igual | Idem, y renombrado sin el «8» |
| `test_alembic_schema_parity` | Mis modelos de test (`_test_modelo_*`) se registran en `Base.metadata`; con `-n auto` cada worker importa todos los módulos y el test los reclamaba como tablas faltantes | `_modelos()` excluye el prefijo `_test_`, con un contra-test que impide que la exclusión tape un modelo real |

Los dos primeros eran **una tercera y una cuarta fuente de verdad** para la lista
de idiomas — exactamente el mismo problema que el selector de `UserProfilePanel`,
que también la llevaba a mano. Ahora las cuatro leen del mismo sitio.

---

## 5.c Dos tests míos que dependían del día en que se ejecutan

Salieron en la suite completa del 2 de septiembre, y los dos son del mismo tipo
que los tres de la sección siguiente: **verificación que había dejado de
verificar**. Los dos los escribí yo en sesiones anteriores.

| Test | Causa | Arreglo |
|---|---|---|
| `test_adhoc_analytics::test_el_filtro_de_fechas_se_aplica_con_cadenas_iso` | Su fixture ponía las imputaciones en `hoy.replace(day=15)`, y el test acota `[primero de mes, hoy]`. **Antes del día 15 las imputaciones caen en el futuro** y quedan fuera con razón. Se escribió a finales de agosto, pasó en verde, y desde el día 1 siguiente mentía | El fixture usa `hoy`, que está siempre dentro del rango, incluso el día 1 |
| `test_timezone_context::test_today_sigue_la_zona_del_contexto` | Afirmaba que Kiritimati (UTC+14) y Niue (UTC−11) difieren 0 o 1 día natural. Son **25 horas** de desfase —lo decía su propio comentario—, así que hay una franja de cada día en que difieren **dos**. Falló a las 10:30 UTC | **Reloj fijo** en el instante que lo hizo fallar, con aserción exacta. Más un segundo test que afirma sólo lo que sí se cumple a cualquier hora: el orden, y que la diferencia no pasa de 2 |

Lo que hay que retener del segundo: la salida fácil era ensanchar la tolerancia
a `(0, 1, 2)` y seguir. Eso habría dejado el test verde y habría dejado intacto
el problema de fondo — que dependía de la hora—, y el siguiente caso raro habría
vuelto a fallar sin explicación. **Un test que lee el reloj real no puede
afirmar una diferencia exacta.**

---

## 6. Ficheros clave añadidos o reescritos

```
app/core/deps.py                    require_superadmin (no existía)
app/core/tenancy.py                 guarda estricta de org_id del cliente
app/db/session.py                   filtro de tenant fail-closed + TenantIsolationError
                                    (2026-08: criterio por variable de cierre —
                                    con el argumento por defecto la 2a org del
                                    proceso no veia nada, ver §3.bis)
app/core/abac_dependency.py         reemplaza al ABACMiddleware borrado
app/core/grc_catalog.py             dimensiones GRC derivadas de las rutas
app/core/grc_enforce.py             matriz GRC aplicada, aditiva-deny
app/core/uploads.py                 perfiles de subida, lectura por trozos
app/core/background.py              spawn() con referencia fuerte
app/core/timeutil.py                zonas, cortes, ContextVar, today()
app/core/timezone_context.py        dependencia async que publica la zona
app/services/revenue_service.py     ASC 606: los tres defectos
app/services/bi_smart_alerts/metrics.py   tabla de despacho (247 → 27)
app/services/automations_service.py       tabla de despacho (38 → 13)
alembic/versions/089_...            las 19 tablas que faltaban
alembic/versions/090_client_timezone.py
alembic/versions/091_rev_entries_unique_batch_period.py
docker-compose.yml                  12 servicios, raíz del proyecto
frontend/nginx.frontend.conf         proxy /api same-origin + WebSocket
frontend/scripts/check_i18n_coverage.mjs  gate bloqueante de cobertura
frontend/scripts/i18n_gap.mjs        medición por idioma
scripts/ci_local.sh                  11 puertas bloqueantes
setup.sh                             alembic upgrade head, volúmenes persistentes
```

Tests nuevos: `test_organization_tenant_isolation`, `test_tenant_filter_fail_closed`,
`test_abac_coverage`, `test_abac_dependency_effective`, `test_upload_security`,
`test_adhoc_analytics`, `test_seed_fixture_parity`, `test_grc_coverage`,
`test_grc_enforcement`, `test_background_tasks`, `test_sso_pkce_nonce`,
`test_simulation_rate`, `test_alembic_schema_parity`, `test_docker_stack`,
`test_timezones`, `test_timezone_context`, `test_revenue_idempotency`,
`test_bi_metrics_catalog`.

**Tests nuevos del hallazgo 18** (uno por función partida; el nombre dice qué
propiedad fijan, y la cabecera de cada fichero explica lo que se encontró al
escribirlos): `test_main_startup_and_logging` (43),
`test_bi_cost_profile_metrics` (18), `test_bi_invoice_metrics` (14),
`test_bi_ticket_metrics` (20), `test_bi_metrics_equivalencia` (4),
`test_profitability_pnl` (26), `test_auto_approval` (24),
`test_user_update_authorization` (13), `test_key_rotation_secrets` (9),
`test_seed_fases` (17), `test_workflow_engine_nodes` (46),
`test_collaboration_notify_filter` (68), `test_ai_call_dispatch` (18),
`test_cmdb_snmp_discovery` (37), `test_overrun_prediction_model` (36),
`test_report_pdf_layout` (19), `test_scim_update_fields` (36),
`test_invoice_pdf_layout` (35) y `test_semantic_suggest_pipeline` (57).

Y una foto congelada: `tests/_fixtures/metrics_pre_refactor.py`, 81 kB del
`metrics.py` anterior al refactor. **Su cabecera dice NO ACTUALIZAR y va en
serio:** existe para que un test compare las 133 claves del catálogo contra la
versión anterior, así que actualizarla al código nuevo lo convierte en un test
que se compara consigo mismo. Lo único que se le cambió respecto al original son
dos imports relativos pasados a absolutos, para poder cargarla suelta.

---

## 7. Orden sugerido para continuar

Quedan **3 de 38** hallazgos en «parcial»: #18 complejidad, #22 acceso a base en
la capa API y #37 las rutas del frontend que no existen. **#37 remedido (§3.ter):
42 métodos huérfanos comparando método y ruta, **hoy 11**. Borrado el cliente
muerto verificado —**53 líneas de método fuera, 11 reescritas**, 42 métodos
netos y 24 funciones de hook—, remapeado lo que tenía
contraparte exacta y arreglado un fallo visible: el Gantt de proyecto se dibujaba
sin dependencias porque el cliente pedía `/dependencies/{id}` en vez de
`/task-dependencies/{project_id}`. Los 11 restantes son endpoints que no existen
y su implementación es decisión de producto.** No son fallos
latentes: son deuda medida. Nada de lo que
queda corrompe datos ni abre un agujero.

**#32, marca blanca: CERRADO.** El documento lleva la marca del tenant y los
cinco generadores están cableados, incluido el de los informes programados que se
envían por correo. Los correos en sí quedan fuera y es scope declarado: son
plantillas HTML y el mecanismo es otro.

**Corrección a lo que decía la versión anterior de este párrafo.** Decía que
nada de lo que quedaba abría un agujero. Era verdad de lo *conocido*, y resultó
insuficiente: al partir tres funciones más aparecieron dos defectos de seguridad
(sección 3.b), y ninguno de los dos se estaba buscando. La conclusión práctica
no es que la auditoría fallara, sino que **partir una función compleja es en sí
mismo un método de detección**: la asimetría entre cinco bloques que hacen lo
mismo, o entre dos evaluadores de la misma condición, sólo se ve cuando están
uno al lado del otro. Por eso el orden de abajo va por riesgo.

1. **#18: haz `apply_filter` y para ahí como tanda dedicada.** El método está
   probado cuarenta y cuatro veces y ha dado once defectos reales, tres de
   seguridad — pero eso fue en las funciones de 18 a 247. De las **ocho más
   grandes que quedan, medido con un script AST, sólo una oculta una tabla de
   despacho**: `apply_filter` (15), 12 `elif` sobre el mismo `operator` en 30
   líneas, y trae defecto (un `in` con valor no-lista devuelve todo sin
   filtrar). Ésa sí vale la pena. Para las otras 96 —entre 11 y 16, largas por
   corrutinas anidadas, bucles sobre grafos o cálculo— **el rendimiento
   decreciente es real y está medido**: pártelas cuando haya que tocar el
   fichero por otra razón, no en una tanda. La tabla de la medición está en la
   sección #18.
2. **#22, los puntos de acceso a base en la capa API** — por dominios, no de
   golpe, cada tanda con su suite. **Tanda 1 cerrada:** `collaboration`, de 127
   puntos a 0 en ocho ficheros, con diez defectos destapados por el camino
   (§#22) y, al verificarlo, un **apagón de datos para toda organización que no
   fuera la primera del proceso** en el filtro de aislamiento (§3.bis).
   **Estado remedido hoy: 95 puntos en 32 ficheros** (204 al cerrar la tanda 1).
   De esos 95, **45 son consultas o escrituras** y **50 son fronteras de
   transaccion** (`commit`/`rollback`), que no son acceso a datos y se tratan
   aparte. Cerradas las tandas de `collaboration` (127 -> 0), `performance`,
   `jira_integration`, `user_costs`, `baselines`, `branding`,
   `workflow_designer`, `governance_ops` y `smart_catalog`.

   Lo que queda, por tamano:

   ```
   service_desk/dynamic_forms.py         9   (5 son commit)
   service_desk/ai_auto_resolution.py    9   orquestacion del trabajo, ver abajo
   service_desk/workflow_designer.py     8   (todos commit)
   service_desk/assets.py                7
   templates.py                          5
   service_desk/connectors_marketplace.py 5
   performance.py                        5   (todos commit)
   client_portal.py                      5
   service_desk/tickets.py               4   dos `db.query(Ticket)` sin acotar
   service_desk/cmdb.py                  4
   esign.py                              4
   ...y 21 ficheros mas con 3 o menos
   ```

   **Dos defectos ya localizados y no arreglados** en lo que queda:
   `service_desk/tickets.py` tiene dos `db.query(Ticket)` sin filtro de
   organizacion, y `service_desk/predictive.py` carga **todos** los tickets
   abiertos sin tope ni acotar. La orquestacion del trabajo de auto-resolucion
   (cerrojo, estado, tarea de fondo, registro del fallo) sigue en el endpoint.
3. **Registrar el escuchador `do_orm_execute` en la factoría de sesiones de los
   tests.** Hoy no se ejecuta en ninguna prueba (§3.bis), que es por lo que el
   apagón vivió sin que nadie lo viera. No se hizo de paso porque activarlo
   cambia lo que ven tests que hoy leen entre organizaciones sin declararlo.
**#16, traducción: CERRADO.** Este documento lo daba por «parcial» y era falso.
Se declaran tres idiomas —`es`, `en`, `zh`, exactamente los que se venden— y los
tres están al **100 %** sobre 3.755 claves, con dos gates bloqueantes: cobertura
con suelo 100 y ausencia de claves duplicadas.

**Dos cosas anotadas y NO tocadas**, porque cambiarlas cambia lo que significa
una cifra y eso es decisión de producto, no de un refactor de complejidad:

- **`timesheet_cost_total` no filtra por estado**: suma el coste de todas las
  hojas de horas, incluidas las **rechazadas** y los borradores. Si la intención
  era el coste comprometido, sobran las rechazadas. Está documentado en la
  cabecera del resolutor en `bi_smart_alerts/metrics.py`.
- **`pending_timesheets` y `timesheets_submitted_count` miran el mismo estado**
  («submitted») y devuelven cosas distintas a propósito: la primera es cuántas
  esperan *ahora*, repetida en toda la serie; la segunda cuántas se entregaron en
  cada mes. Es correcto, pero no es evidente leyendo el código, así que ahora
  está escrito.

Lo demás yo lo dejaría donde está, y digo por qué:

- **Consolidar las cuatro librerías de gráficos en una.** El coste de carga ya
  está resuelto (#19: −68 % al abrir las páginas afectadas), así que migrar 25
  usos de echarts y 18 de recharts es riesgo alto por beneficio hoy marginal.
- **`echarts` 5→6 y `react-router-dom` 6→7** — los 3 avisos `moderate` de
  `npm audit`. Cada uno es una migración con riesgo sobre 119 rutas lazy.

  **Corrección del 2 de septiembre:** el gate bloqueante está en nivel `high`, y
  cuando se escribió esto estaba a 0 — pero para entonces **ya había aparecido un
  `high` nuevo**: `browserslist`, transitiva vía `autoprefixer`, `@babel/core` y
  `webpack`. Arreglado con un salto de **parche** (4.28.2 → 4.28.8) tocando sólo
  el lockfile; `package.json` no cambia. Ahora `high` y `low` están a 0 y quedan
  los 3 `moderate`.

  Lo que hay que retener: **`npm audit` cambia sin que nadie toque el código.**
  Una frase como «está a 0» caduca sola. Conviene ejecutarlo antes de cada tanda,
  no confiar en lo que diga este documento.
- **`strictNullChecks` (226) y `noImplicitAny` (387).** El camino es la whitelist
  de `tsconfig.strict.json`: añadir ficheros y dejar el gate verde.
