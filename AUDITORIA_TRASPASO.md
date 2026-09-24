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

# Duplicacion: parejas de funciones casi identicas, para mirarlas. NO falla
# nunca; la duplicacion no tiene un numero que deba ser cero. Es el barrido que
# destapo la copia del dominio de tareas sin ABAC y los dos generadores de
# factura con NIF distinto.
./.venv/Scripts/python.exe scripts/audit_funciones_duplicadas.py

# Complejidad: informe legible de las funciones por encima de 10. NO falla nunca
# —el que bloquea es `tests/test_complejidad_no_empeora.py`, dentro de la suite—;
# esto es para elegir la siguiente sin ir a buscarla.
./.venv/Scripts/python.exe scripts/audit_complejidad.py
# Y para regenerar la lista del trinquete despues de una mejora:
./.venv/Scripts/python.exe scripts/audit_complejidad.py --lista

# La suite completa. Aviso de entorno (2026-09-15): con `-n auto` los
# trabajadores de xdist se quedaban colgados —arrancan y no consumen CPU—, y en
# un solo proceso no termina en ninguna ventana razonable. Con `-n 4` va.
./.venv/Scripts/python.exe -m pytest -q --no-header -p no:randomly -n 4 > /tmp/suite.txt 2>&1

# Frontend
cd frontend
npx tsc --noEmit          # tiene que salir limpio
npm run test              # vitest
node scripts/check_i18n_coverage.mjs   # gate de cobertura de traducción

# Todas las puertas de golpe (10 bloqueantes + informativas)
bash scripts/ci_local.sh
```

**Estado en la última verificación completa (2026-09-15):**
**3765 passed, 19 skipped, 1 xfailed, 0 fallos** con `-n 4`;
`ruff check app tests` limpio; `tsc` limpio; **92/92 vitest**; `npm audit` en
**cero**; `typecheck:strict` **0 errores en 338 de 338 ficheros, tests
incluidos** (§3.sexvicies); y **ninguna función de `app/` por encima de
complejidad 10** (§3.septvicies) — los dos hallazgos que llevaban toda la
auditoría abiertos, cerrados.

**Y la suite tarda ahora 8 minutos en vez de 40** (§3.novovicies): tardaba
preparándose —392 tablas creadas y destruidas y cuatro hashes bcrypt por test—,
no ejecutando.

> Y es la primera vez que ese «0 fallos» se mide **con la semántica de tenant de
> producción puesta** (§3.sexdecies). La primera pasada con los escuchadores
> registrados dio **23 en rojo**: catorce del propio banco de pruebas, dos
> regresiones de la jornada y **siete defectos de producción** (§3.vicies).
>
> **Advertencia de entorno, segunda parte: cómo saber si la suite avanza.**
> En esta máquina, `Get-Process python | Measure-Object CPU -Sum` de PowerShell
> **no sirve para eso**. Da cifras absurdamente bajas: cuatro procesos `pytest`
> ejecutando tests a buen ritmo —con sus registros creciendo 410 bytes en 40
> segundos— reportaban **0,875 s de CPU acumulados entre los cuatro**. Dos
> órdenes de magnitud por debajo de la realidad.
>
> Eso llevó a declarar colgada una pasada de 33 minutos que muy probablemente
> estaba sana, y a matarla. Dos señales que **tampoco valen**:
>
> * **Que los procesos existan.** Un proceso colgado existe igual de bien que
>   uno trabajando.
> * **Que el fichero de salida esté vacío**, si el comando va canalizado
>   (`| tail`, `| head`): esos filtros no escriben nada hasta el final, así que
>   cero bytes a los treinta minutos es lo esperado y no dice nada.
>
> **La señal que sí funciona es cuánto CRECE el registro**, y para eso hay que
> escribir a fichero con `>` y no canalizar. Con `pytest` sin `-q` el avance se
> escribe según ocurre, con su porcentaje.
>
> Lo mismo dicho al revés, que es como conviene recordarlo: *antes de declarar
> que algo está parado, comprobar que el instrumento mide*. Aquí el instrumento
> no medía, y el diagnóstico fue una invención con aspecto de dato.

> **Y una advertencia de entorno que costó una jornada:** `pytest-xdist` con
> `-n auto` se quedaba colgado en la máquina de desarrollo —los trabajadores
> arrancan y no consumen CPU, tanto con `-n auto` como con `-n 2` sobre un solo
> fichero—, y en un proceso la suite no cabe en ninguna ventana razonable. Con
> **`-n 4` arranca y termina** (50 min). Si vuelve a pasar, ése es el camino: no
> es el código.

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

## 3.quindecies El hallazgo 37, cerrado: de 62 a 11 y de 11 a 0

`DESAJUSTES_CONOCIDOS` en `tests/test_rutas_del_frontend.py` está en **cero**, y
cero es ahora el suelo: si sube, hay una pantalla nueva que no puede funcionar.

Los once que quedaban **no eran un grupo homogéneo**, y por eso ninguno se
arregló igual. Esa es la parte que importa: «implementar los endpoints que
faltan» habría sido la respuesta equivocada a cuatro de los cinco casos.

### Cuatro `GET` de detalle: el CRUD completo menos leer uno

`contractsApi`, `risksApi` y `usePipeline` tienen listar, crear, actualizar y
borrar; **leer uno era la única cuya ruta no estaba**. No hubo nada que
inventar: la búsqueda acotada y el serializador son los que ya usan el `PATCH` y
el `DELETE` de al lado.

En el de riesgos, además, la decisión de **no** poner comprobación de rol está
escrita: editar y borrar exigen admin o PM, leer no — quien puede ver el registro
de riesgos del proyecto puede ver uno de ellos, y exigir un rol aquí dejaría la
lectura de uno por detrás de la lectura de todos.

Y en el de oportunidades la búsqueda estaba **copiada literalmente tres veces**
—`update_opportunity`, `delete_opportunity` y
`convert_opportunity_to_project`—, así que se extrajo a `oportunidad_propia` y
las tres la usan. Su `is_active == True` no es decorativo: el borrado de una
oportunidad es lógico, y sin ese filtro una ya borrada volvería a aparecer.

### Dos manejadores escritos, completos, y sin registrar

`update_certification` y `delete_certification` **existían**, con su
comprobación de permisos —sólo el dueño de la certificación, o admin/RRHH— y
**sin decorador de ruta**. No eran endpoints que faltaran: eran endpoints que
nadie registró. Arreglarlo fue añadir dos líneas.

Y esa pregunta vale para todo el repositorio, así que se hizo: un barrido por
AST sobre `app/api/` buscando funciones con pinta de manejador —reciben
`Depends`, `Query`, `Body`…— y sin decorador de ruta. **Son los dos únicos
casos.** Las otras dos que salen son dependencias (`get_current_client`,
`require_admin_or_pm`) y están bien así.

### Tres borrados que no hacían nada, y ninguno se resuelve borrando

Los dos «botones silenciosos» que la auditoría llevaba anotados, más uno:

* un **problema** es el registro de una investigación, con su análisis de causa
  raíz, sus incidentes vinculados y su posible entrada en la base de errores
  conocidos. Borrar la fila dejaría huérfano todo eso: **se cierra**.
  `ProblemStatus` no tiene `cancelled`, así que el estado terminal es `closed`;
* un **cambio** es un registro de gobernanza con aprobaciones, ventana de
  mantenimiento y plan de rollback: **se cancela**, que sí es un valor de
  `ChangeStatus`. Y uno ya implementado responde **409** — cancelar lo que ya
  pasó sería reescribir la historia, y el conflicto es con el estado del
  recurso, no con la petición;
* una **integración OAuth** guarda su historial de sincronización, que sirve
  para diagnosticar: **se desactiva** —`is_active`, la convención del
  repositorio— **y se borran los tokens**. Eso último es lo que de verdad hay
  que quitar: dejar un `access_token` de un tercero en una fila desactivada es
  guardar una credencial que ya no se usa.

Los tres son idempotentes, y los tres tienen test de que lo son.

### El listado de tickets de un Known Error

El modelo ya estaba: la tabla de unión `sd_known_error_tickets` con
`known_error_id` y `ticket_id`. Sólo faltaba exponerlo. La guarda es la del
problema, porque un Known Error es un `Problem` promovido.

> La ruta va **después** de `/known-errors/stats` y de los dos `run-*-scan`, y
> lo mismo en el de oportunidades respecto a `/pipeline` y
> `/proposals/templates`. FastAPI resuelve por orden de declaración, así que un
> `/{id}` puesto antes se tragaría esas rutas literales. Es el defecto de §3.g
> —ocho rutas inalcanzables porque otra las tapaba— y no se repite.

### Y los dos exports, que eran un error del cliente

`ExportsPage` llamaba a `POST /integrations/export/imputations` y
`/integrations/export/projects`, y **ninguna de las dos está en ningún router**.

* El de **imputaciones sí existía**, con otro verbo y otra ruta:
  `GET /analytics/exports/imputations-csv`. El arreglo es en el cliente.
* El de **proyectos no existía**. El export de *recursos* que hay no sirve:
  exporta instantáneas de utilización por persona y semana, no proyectos. Se
  añade `GET /analytics/exports/projects-csv`, con el ámbito de
  `scope_projects_query` —el mismo del listado, así que un gestor exporta lo que
  ya ve en pantalla— y con `include_costs` opcional y **por defecto apagado**,
  porque son importes.

**Y un defecto de propina al mirarlo:** el export de imputaciones hacía
`imp.task.name`, y `Task` tiene `title`. Reventaba con `AttributeError`, así que
**fallaba en cuanto una imputación tenía tarea** — que es el caso normal. Este no
lo encuentra `audit_instance_attrs.py`: `imp` viene de una llamada a un
servicio, y ahí el detector no infiere el tipo. Es exactamente el límite que su
cabecera declara.

Y una honestidad sobre el formato: esa pantalla tiene un selector CSV/XLSX y el
backend **sólo sirve CSV**. La extensión del fichero descargado sale ahora del
formato real y no del botón pulsado — un fichero llamado `.xlsx` con CSV dentro
es peor que uno llamado `.csv`. El selector sigue en pantalla y no tiene
contrapartida: **queda anotado, no arreglado**, porque generar XLSX es trabajo
de producto.

## 3.quinvicies El bearer de Teams, el XLSX que no existía, y cuatro funciones más

Tres cosas que la auditoría llevaba anotadas y una cuarta que salió al hacerlas.

### El bearer de Teams no verificaba la firma

El receptor de comandos decodificaba el cuerpo del JWT **sin verificar nada** y
comparaba `aud`/`appid` con `TEAMS_BOT_APP_ID`. La propia auditoría lo dejó
escrito con todas las letras —«es una comprobación de destinatario, no de
emisor: frena un token de otro bot, no uno fabricado»— y esa nota describía un
agujero real:

> el id de aplicación de un bot **no es un secreto**, así que cualquiera que lo
> supiera podía escribir un JWT a mano, sin firmar, y el receptor lo aceptaba y
> ejecutaba el comando.

Ahora se verifica la firma contra las claves públicas de Bot Framework, más el
emisor, la audiencia y la caducidad — y las cuatro las hace `jwt.decode`, no se
comprueba ninguna a mano, que es donde se cuelan los fallos. El cliente de
claves se cachea por URL: sin eso habría una llamada a Microsoft en **cada**
comando entrante.

**Dos ajustes nuevos, y no constantes:** `TEAMS_BOT_OPENID_METADATA_URL` y
`TEAMS_BOT_ISSUER`. Las nubes soberanas de Microsoft —government, China—
publican sus claves en otro dominio, y con la URL a fuego el bot no se podría
desplegar ahí. Documentados en `.env.example`.

Y el mensaje de error es **el mismo para todos los modos de fallo**. Distinguir
«firma inválida» de «audiencia equivocada» en la respuesta le dice a quien lo
intenta qué parte ya tiene bien; el detalle va al registro, que es donde sirve.
Un test existente exigía que el mensaje dijera «audience» y se alineó **con su
razón escrita**, que es distinto de relajarlo.

Lo que **no** cubre, dicho para que no haya que adivinarlo: no se compara el
`serviceUrl` del cuerpo con el del token. Bot Framework lo documenta como paso
adicional y sirve para que un bot no reenvíe respuestas a un servicio ajeno;
aquí no se reenvía nada, se responde en el mismo ciclo HTTP.

### El selector CSV/XLSX que no tenía contrapartida

La pantalla de exportaciones ofrecía XLSX desde siempre y el servidor **sólo
servía CSV**. En agosto se hizo lo honesto mientras tanto —que la extensión
saliera del formato real y no del botón pulsado, porque *un fichero llamado
`.xlsx` con CSV dentro es peor que uno llamado `.csv`*— y quedó anotado.

Y había una segunda mentira más silenciosa: el botón de proyectos decía
literalmente **«Descargar Excel de proyectos»** y devolvía un CSV.

`app/services/exportador_tabular.py` sirve los dos formatos. `openpyxl` ya era
dependencia, así que el trabajo no era generar la hoja: era **no escribir dos
veces cada export**. Decisiones que merecen quedar dichas:

* **la extensión la pone el exportador, no quien llama** — es medio motivo de
  que el módulo exista: mientras el nombre lo escribiera cada sitio, podía decir
  una cosa y el contenido otra, que es exactamente el defecto que cierra;
* **el CSV lleva BOM**, o Excel destroza los acentos y eso se reporta como «el
  export está roto»;
* **los números van como números y las fechas como fechas** en la hoja: quien
  pide un Excel lo pide para sumar;
* **un formato desconocido es 400**, no un CSV por defecto. Devolver otra cosa
  de la que se pide es el defecto que esto viene a cerrar.

### Y cuatro funciones más del hallazgo 18

**74 funciones** sobre el umbral, exceso **173**. No se han partido por el
número: las seis tenían costura con nombre.

* **`send_message`** (16 → bajo el umbral): autorizar según quién escribe
  —cliente de portal, bot o usuario, y cada uno por una vía distinta—, enganchar
  al hilo, y crear las menciones. Tres conceptos, tres funciones.
* **`_project_internal_cost`** (16 → bajo el umbral): la cascada de fuentes del
  coste y la búsqueda del coste/hora vigente en una fecha. Esa última tiene una
  regla de desempate que ahora está escrita donde se puede leer: si ninguna
  vigencia contiene la fecha, se usa el perfil abierto más reciente, y el
  `coverage_pct` que devuelve la función dice cuánto del número se calculó así.
* **`stop_timer_session`** (15 → bajo el umbral): validar la parada —que se
  revalida **al parar y no al arrancar**, porque entre una cosa y otra pueden
  pasar horas y al usuario le pueden haber sacado del proyecto—, calcular las
  horas con sus tres sutilezas (pausas, cambio de medianoche y mínimo de cuarto
  de hora) y las dos guardas que comparte con el alta manual.
* **`GuardrailEngine.evaluate`** (15 → bajo el umbral): tres guardarraíles
  —palabras vetadas, tope de tokens, datos personales— y, sobre todo, **el
  bloque de «construir el resultado bloqueado, auditar y devolver» escrito tres
  veces**. Tres copias del camino de denegación en una función de seguridad es
  justo donde no se quieren tres copias; ahora cada revisor devuelve el motivo y
  el resultado se construye una vez.
* **`check_document_access`** (14 → bajo el umbral): «qué nivel tiene esta
  persona sobre este documento» es una pregunta con nombre. Al separarla quedó
  escrito lo que estaba implícito: un permiso que no declara ni usuario ni rol
  ni departamento está **mal formado y se descarta**, que es la diferencia entre
  un fallo de datos y un agujero.
* **`critical_path_payload`** (16 → bajo el umbral): las cinco fases del CPM
  **tienen nombre de libro** —grafo, orden topológico, pasada adelante, pasada
  atrás—, así que el cuerpo principal se lee ahora como el algoritmo que es. Y
  al separarlo quedó escrito un detalle que estaba implícito: las tareas que
  forman un ciclo **se añaden al final en vez de descartarse**, porque un
  diagrama al que le faltan filas sin decir por qué es peor que uno con un ciclo
  visible.

## 3.quatervicies ABAC por recurso concreto, que no existía

Toda la API paseaba el `resource_id` hasta el motor de políticas —233 endpoints
llaman a `enforce_abac(db, user, "task", task.id, action="update")`— y **el motor
no lo miraba**. `ABACService.evaluate_access` lo recibía, lo guardaba en el
detalle de auditoría y decidía sólo con el rol, el `resource_type` y los
atributos del usuario; `is_policy_applicable` ni siquiera lo aceptaba. Con
`action` pasaba lo mismo.

Consecuencia: una política sólo podía decir «los de este rol no tocan tareas».
Nunca «no tocan las tareas del proyecto X», ni «pueden leer pero no borrar».

### Cómo salió, que es la mejor parte

De un test que iba a demostrar otra cosa. Al de-duplicar el dominio de tareas
(§3.novodecies) escribí que `POST /tasks/bulk-update` se saltaba ABAC, y monté
el test que lo demostraba. **Demostró lo contrario**: la ruta devolvía 403 antes
de entrar al manejador, porque la comprobación «por tarea» y la del router daban
el mismo veredicto. Y sólo podía ser por una razón — que el `resource_id` no
entraba en la decisión.

Quedó anotado como «diseño de producto, no se toca en una tanda de otra cosa».
Esta es esa tanda.

### Qué se ha hecho

`app/services/abac_recursos.py` resuelve los atributos de la fila concreta y los
mete en el espacio de nombres de evaluación con el prefijo `recurso.`; `accion`
entra como una clave más. Una regla puede ahora escribirse así:

```json
{"attribute": "recurso.project_id", "operator": "equals", "value": "p-123"}
{"attribute": "accion",             "operator": "equals", "value": "delete"}
```

**Tres decisiones que merecen quedar escritas:**

* **La superficie está declarada.** `TIPOS` es un mapa explícito de tipo de
  recurso a modelo; no se descubre recorriendo el registro de SQLAlchemy, aunque
  se podría. Esto es una función de seguridad, y en seguridad la superficie se
  declara: añadir un tipo es una línea, y esa línea **es** la decisión de
  exponerlo.
* **Las columnas que huelen a secreto no se exponen** —`password`, `token`,
  `secret`, `key`, `hash`, `salt`, `credential`—. El valor de una regla acaba en
  el registro de auditoría y las políticas las edita un administrador de cliente
  desde la interfaz: filtrar aquí es más barato que confiar en que nadie escriba
  esa regla.
* **Un recurso que no se resuelve no encaja**, ni para permitir ni para denegar,
  y se registra. Es coherente con que `enforce_abac` sea fail-open por diseño
  —lo dice su propia cabecera— y con no convertir un id inexistente en una
  denegación silenciosa de todo.

### Compatible hacia atrás por construcción, y probado

Lo único que hace el cambio es **añadir** claves al diccionario de evaluación, y
están prefijadas para que no puedan chocar con un atributo de usuario. Una
política que sólo mira atributos de usuario ve exactamente lo que veía.

Eso importa tanto como lo nuevo: un cambio en un motor de autorización que
altere en silencio lo que ya estaba decidido es peor que el hueco que venía a
cerrar. Hay un test que lo fija —mismo veredicto con y sin `resource_id` cuando
la regla no lo nombra— y los **103 tests ABAC existentes pasan sin tocar uno**.

### Y dos notas que decían lo contrario, corregidas

`abac_dependency.py` decía que `action` era «informativo, como antes:
`enforce_abac()` no lo pasa a `evaluate_access()`». Era cierto y ya no lo es. Lo
que sigue siendo cierto es que esa dependencia **no conoce el `resource_id`**
—sabe el prefijo de la ruta, no qué fila se toca—, así que ahora sí es verdad
que las llamadas explícitas de los endpoints aportan grano más fino: es lo que
esa nota afirmaba antes sin que lo fuera.

## 3.tervicies Las tres decisiones de producto que quedaban anotadas

La auditoría dejó tres columnas en «anotado y no inventado», y era la postura
correcta en su momento: las tres salieron del detector `audit_model_attrs.py`
—código que nombraba atributos que el esquema no tenía— y **las tres reventaban
con `TypeError` en la primera línea útil**. Se arregló el síntoma y se dejó
escrito que añadir la columna era decisión de producto, no de aquel arreglo.

La revisión **096** toma las tres decisiones. Cada una con su criterio escrito,
porque un criterio escrito se puede discutir y uno implícito no.

### `sd_tickets.requester_phone`

El servicio de SMS entrantes construía el ticket con `requester_phone=...`
detrás de un `hasattr` que protegía el valor y no la palabra clave, así que
**abrir un ticket desde un SMS fallaba siempre**. El teléfono acababa de rebote
en `requester_name` y en la descripción.

**Criterio:** en un ticket abierto por SMS el teléfono **es** la identidad de
quien lo abre — sin él no hay a quién responder. Eso es un campo, no una nota.
Nullable, porque los tickets de otros canales no lo tienen.

### `imputations.work_type`

La importación de imputaciones desde CSV lo pasaba al constructor y **fallaba
fila por fila**.

**Criterio:** no se está inventando un concepto, se está creando el sitio donde
guardar uno que ya se usa — el catálogo de informes lo ofrece como campo y
`billing_reports_service` lo lee con un respaldo a «development». Y **el
respaldo no baja a la fila**: quien no informe el tipo se queda sin él. Escribir
«development» en la fila convierte un dato ausente en un dato afirmado, y eso no
se deshace.

### `sd_tickets.major_incident_id`

La única de las tres con una decisión de forma detrás, y por eso la que más
merecía esperar.

**Criterio: un ticket pertenece como mucho a UNA incidencia mayor**, y una
incidencia mayor agrupa muchos tickets. Es el modelo de ITIL y es el
conservador: una tabla de unión permitiría que dos incidencias mayores
compartieran tickets, y eso hay que **quererlo explícitamente**, no heredarlo de
haber elegido por costumbre la estructura más flexible. Si mañana hace falta,
pasar de una clave foránea a una tabla de unión es una migración; al revés se
pierden datos.

`ON DELETE SET NULL` y no `CASCADE`: borrar la declaración de una incidencia
mayor **no** puede llevarse por delante los tickets, que son el trabajo real.

**Y la comprobación de cumplimiento vuelve a funcionar sin tocar una línea de
ella.** `governance_compliance_service` ya estaba escrito contra
`MajorIncident.tickets`; como la relación no existía, «P1 sin incidencia mayor
declarada» estaba declarada **no evaluable** — mejor eso que un falso positivo
por cada P1. Ahora se puede evaluar.

### El guardián pidió que le quitaran su propia excepción

`tests/test_atributos_de_modelo_existen.py` tenía un segundo test que comprueba
que **cada excepción declarada siga siendo necesaria**. Al añadir la relación se
puso en rojo: «estas excepciones ya no hacen falta, el atributo existe». Es
exactamente para lo que estaba, y es la diferencia entre una lista de
excepciones y un cajón de sastre.

**`CONOCIDOS` queda vacía por primera vez.**

### Verificación

La migración se verificó **ejecutándola**: partiendo de un esquema sin las tres
columnas, comprueba que se añaden, que son nullable, que el índice está, que se
puede escribir y leer en las tres, que una segunda pasada no revienta y que el
`downgrade` las quita. Más 22 tests en verde entre los nuevos y los guardianes.

---

## 3.sexvicies El modo estricto llega a 338 de 338, y lo que había debajo

La lista blanca de `tsconfig.strict.json` iba por 284 de 338 ficheros y 311
errores. Hoy cubre **todo `src/`, tests incluidos, con cero errores**, y el
fichero de migración gradual ha dejado de existir como tal.

Lo que importa de esta pasada no es el número: es **lo que apareció al tipar**.
Un modo estricto no «arregla» nada por sí solo; lo que hace es obligar a
escribir suposiciones que hasta entonces vivían en la cabeza de quien escribió
el código. Ahí es donde salieron los defectos.

### Lo que el gate escondía

Dos cosas, y las dos importan más que los 311 errores:

**1. La lista blanca nombraba 27 ficheros de test que nunca se comprobaron.**
El `exclude` del `tsconfig.json` base descarta `**/*.test.ts(x)`, y en
TypeScript `exclude` gana sobre `include`. Así que el gate decía «284 ficheros»
y comprobaba 257. Al meterlos de verdad salieron **36 errores** más, uno de
ellos un test que pasaba `entityType` / `entityId` a `DocumentsPanel` —props que
ese componente **no tiene**— y por tanto renderizaba el panel sin ninguna
entidad; pasaba igual, porque lo único que comprobaba es que hubiera un primer
hijo.

**2. El filtro de `check_strict.mjs` se habría vuelto ciego.** El script leía la
lista `include` y sólo contaba errores de esos ficheros. Al pasar `include` a
globs (`src/**/*.ts`), la comparación por nombre de fichero no habría encajado
con **ninguno**, y el gate habría dado por bueno un proyecto con cualquier
número de errores. Se ha quitado el filtro entero: ahora `tsc` manda sobre todo
el proyecto y el script sólo traduce su salida. **Validado rompiéndolo**: un
fichero *nuevo* con un `any` implícito lo tumba (salida 1), y limpio da 0 — que
es justo el agujero que tenía la lista, donde un fichero nuevo no contaba hasta
que alguien lo añadiera a mano.

### Los defectos que destapó tipar el kit de UI

`src/components/ui/index.tsx` es el kit que usa toda la aplicación y **no
declaraba ni una sola prop**: la mitad de los componentes llevaban `: any` en la
desestructuración y la otra mitad ni eso. Declararlas bajó ese fichero de 37
errores a 7 **sin romper una sola llamada**, y sacó cuatro fallos reales que
llevaban tiempo ahí, todos de la misma familia — *props que se pasaban y nadie
leía*, que React descarta en silencio:

| Lo que se pasaba | Dónde | Qué pasaba de verdad |
|---|---|---|
| `Modal size="lg"` | 8 llamadas | `Modal` no tenía `size`. Ocho modales que pedían ser anchos salían con los 520 px por defecto. |
| `EmptyState subtitle=` | 2 llamadas | El componente lee `description`. Ese texto no se ha visto nunca. |
| `EmptyState message=` | 3 llamadas | Lo mismo. |
| `Card className=` | 1 llamada | `Card` no reenviaba la clase al `div`: no llegaba al DOM. |

`size` se ha **implementado** (lo que pedían era legítimo y estaba escrito);
`subtitle` y `message` se han corregido en las llamadas, porque dos nombres para
lo mismo es como empieza este tipo de fallo.

Y uno más, de otra clase: `Button` escribía `gap: s.gap` y tres líneas después
`...s`, que vuelve a poner `gap`. Código muerto, destapado por `TS2783`.

### El fallo más serio: un hook que leía haciendo POST

`useTaskComments` llamaba a `tasksApi.comment(id, null)` —un **POST** a
`/tasks/{id}/comments`, que es el endpoint de *crear* un comentario— para
*leerlos*. No existe endpoint GET de comentarios de tarea. El hook **no ha
funcionado nunca**: el `.catch(() => [])` se tragaba el error y devolvía una
lista vacía, indistinguible de «no hay comentarios».

Se ha **borrado**, no arreglado: está exportado y no lo llama ni un sitio. Crear
un endpoint de backend para un hook que nadie usa sería escribir más código
muerto, esta vez con bendición.

### Dos decisiones de comportamiento, escritas a propósito

Tipar obliga a contestar preguntas que el código esquivaba. Dos respuestas
cambian lo que se ve en pantalla, y van dichas aquí para que no se lean como un
efecto colateral:

- **`ProfitabilityPage`: un margen que falta ya no se pinta verde.** Los 20
  errores de ese fichero eran la misma pregunta —«¿de qué color pinto un margen
  que puede no venir?»— y la respuesta que daba el código era, sin querer,
  *verde*: en JavaScript `undefined < 0` es `false`, así que un dato ausente
  caía en la rama buena de cada ternaria. Ahora es **neutro**. Un dato que falta
  no es un dato bueno, y en una pantalla de rentabilidad esa diferencia se lee
  como una afirmación sobre el negocio.
- **`ValidationResult<T>` es una unión discriminada.** Declaraba `success` y
  `data` como campos independientes, así que la invariante «si validó, hay
  datos» vivía en la cabeza de quien lo escribió. Escribirla arregló cuatro
  sitios a la vez.

### Duplicación que apareció de paso

- `PortalUsersTab` tenía la lista de permisos del portal **escrita dos veces**:
  la constante tipada `PORTAL_PERMISSIONS` en el formulario de edición y una
  copia a mano, sin tipo, en el de alta. Añadir un permiso en una y no en la
  otra era cuestión de tiempo.
- `ChangesPage` tenía una copia local de `IMPACT_CFG`, palabra por palabra, que
  sombreaba la del módulo.
- `ResourceForecastPage` repetía la cadena de umbrales de carga —100 / 85 / 50 /
  10— **tres veces** en el mismo fichero. Ahora es `estadoDeCarga()`.

Las tres eran reglas de negocio que se podían cambiar en un sitio y quedarse mal
en otro sin que nada avisara.

### El guardián de plotly, reescrito por un motivo de tipos

Leía el disco con `node:fs` y `__dirname`, lo que obligaba a meter `@types/node`
en la compilación. Y una `/// <reference types="node" />` **no es local al
fichero**: vale para el programa entero. Con ella cargada, `window.setTimeout`
se resuelve contra la declaración de Node y devuelve `NodeJS.Timeout` en vez de
`number`, y `PortalClientePage` —que guarda el identificador con el idioma
correcto— dejaba de compilar. Un fichero de test no puede cambiarle los tipos al
navegador.

Ahora usa `import.meta.glob` con `?raw`: nativo de Vite, el contenido lo inlinea
el bundler, no hay E/S en ejecución y no necesita un solo tipo de Node. Se le ha
añadido **un tercer test que vigila al guardián**: comprueba que el barrido
encuentra el árbol. Hizo falta de inmediato — la primera versión buscaba la
clave `../../charts/PlotlyCustom.ts` y Vite la devuelve como
`../PlotlyCustom.ts`, normalizada a la ruta relativa más corta. Sin ese tercer
test, los otros dos habrían pasado sin mirar nada.

**Validado rompiéndolo**: un componente nuevo con `import Plot from
'react-plotly.js'` lo tumba y aparece por nombre en el mensaje.

### Cómo queda el gate

`tsconfig.strict.json` ya no es una lista: cubre `src/**` con `exclude`
reducido a `node_modules` y `dist`, para que los tests entren. El objetivo
siguiente, ya sin migración de por medio, es mover esos flags a
`tsconfig.json` y borrar el fichero; mientras el base siga en `strict: false`
—lo usa `npm run typecheck`, y ahí conviven aún ficheros `.mjs` sin tipar— el
estricto es el que manda para el gate.

**Verificado:** `npm run typecheck:strict` 0 errores · `npx vitest run` 27
ficheros, **92/92** · `npm run build` correcto.

## 3.septvicies La complejidad llega a cero, y dos guardianes que no medían

`scripts/audit_complejidad.py` dice hoy **«Ninguna función de `app/` por encima
de 10.»** Se llegó ahí desde 94 / 253 / 17 (funciones / exceso / máximo),
pasando por 74 / 173 / 16 al empezar esta pasada.

**Y ninguna se arregló partiéndola para bajar un número.** Eso es lo único que
hace interesante el cero: casi todas eran una de dos cosas.

### Una tabla escrita como cascada de `if`

Los bytes mágicos de un fichero. Las palabras clave de un triaje de tickets —dos
tablas, y como tabla se ve que ninguna palabra se repite entre grupos, que era
imposible de comprobar antes—. Las once reglas de una retrospectiva. Los nueve
operadores de una expresión de flujo. Los **19 pasos** de un plan de pruebas
(197 líneas) y los **15 avisos** de un plan de comunicación (260). Los cinco
tipos de aprobador —y como tabla se ve que **no hay ninguna vía que dé paso a un
administrador por serlo**, que es deliberado—. Los pesos de un cálculo de riesgo
de sesión. Las seis recomendaciones de cumplimiento con su umbral. El espejo de
campos trabajador→usuario. El catálogo de diez informes del sistema.

Un plan de pruebas **es** una tabla. Verlo entero es lo que hace falta para
revisarlo con quien lo va a ejecutar, y añadir un paso pasa a ser añadir una
fila en su sitio en vez de una rama en medio de un bloque de 200 líneas.

### El mismo bloque escrito dos o más veces

| Dónde | Cuántas veces |
|---|---|
| El diccionario de respuesta de `analytics.run_query` | **tres** |
| El `try/except` de registro de `ai_providers.test_provider` | **cuatro** |
| El respaldo a JSON de `bi_collaboration.resolve_comment` | dos |
| La aritmética de solapamiento de reservas en `get_advanced_utilization` | dos |
| DocuSign y Adobe en `create_provider_envelope` (40 líneas cada uno) | dos |
| La lista de permisos del portal en `PortalUsersTab` | dos |
| La cabecera + filas + autoajuste de las hojas de Excel | cuatro |
| La cadena de umbrales de carga de `ResourceForecastPage` | **tres, en el mismo fichero** |
| La respuesta «ya está corriendo» del trabajo de auto-resolución | dos |

### Defectos que nadie estaba buscando

* **`useTaskComments` leía haciendo POST.** Llamaba al endpoint de *crear* un
  comentario, con cuerpo nulo, para *leerlos*. No existe endpoint de lectura. El
  `.catch(() => [])` se tragaba el error y devolvía lista vacía, indistinguible
  de «no hay comentarios». Borrado: estaba exportado y no lo llamaba nadie.
* **El refinamiento con Claude de `estimate_task_hours` nunca se ejecutó.**
  Construía el contexto con `for t in similar_tasks[:5]` leyendo `t.title` y
  `t.actual_hours`, pero `similar_tasks` son filas `(Task, horas_reales)`:
  `AttributeError` sobre la fila, y `actual_hours` es la columna que el hallazgo
  de 2026-08 ya documentó como inexistente. Las dos excepciones caían en un
  `except Exception` que registraba un aviso y seguía. Resultado correcto por
  accidente, rama muerta en la práctica.
* **El chequeo SSRF de las automatizaciones se distinguía por el texto del
  mensaje.** Dos `raise ValueError` que se atrapaban a sí mismos y se separaban
  con `"Solo se permiten" in str(e)`. Cambiar una palabra del mensaje habría
  roto el control sin que nada avisara.
* **Código muerto en la predicción de sobrecoste**: dos expresiones
  `x = ... if hasattr(start, "days") or True else 30`, cuyo `or True` hace la
  condición siempre cierta y cuyo resultado se pisaba dos líneas después.
* **`Modal size="lg"`, `EmptyState subtitle=`/`message=`, `Card className=`** —
  props que se pasaban y nadie leía. Ver §3.sexvicies.

---

## 3.octovicies Los dos guardianes que no podían fallar

Esto es lo más incómodo de la jornada y lo que más conviene leer.

### El guardián de cobertura ABAC se satisfacía a sí mismo

`tests/test_abac_coverage.py` comprueba que ninguna ruta tenga `enforce_abac()`
como **único** control —porque `enforce_abac` es *fail-open*: sin políticas
activas, que es el caso por defecto, no comprueba nada—. Pasaba en verde con
cero rutas señaladas.

Era mentira. `_called_service_sources` resuelve cada nombre que el endpoint
llama, concatena su código fuente, y busca ahí señales de autorización
(`user.role`, `is_superadmin`, `HTTPException(403)`...). **`enforce_abac` es uno
de esos nombres**, y su cuerpo contenía `is_superadmin` y `user.role`. Así que
toda ruta cuyo único control fuera `enforce_abac` quedaba tapada por el propio
`enforce_abac`. El guardián no podía fallar por el motivo exacto que existe para
detectar.

Salió al bajar la complejidad de `enforce_abac`: al mover el corte de superadmin
y el 403 a dos ayudantes, las señales desaparecieron de su cuerpo y el test se
puso rojo de golpe sobre **65 rutas**. No era una regresión — era la primera vez
que medía.

### Y de las 65, cuarenta y una eran fallo del propio detector

Aquí está la parte que importa, y es la misma lección otra vez: **antes de
actuar sobre un número, comprobar que el instrumento mide**.

Las 65 se quedaron en 54 al reconocer la comprobación de propiedad
`..._for_user(db, id, current_user.id)`. Al empezar a arreglar las 54 una por
una, leyendo el código, resultó que **la mayoría ya tenían control** y el
detector no lo veía. Tres defectos suyos, los tres reales:

1. **Resolvía los nombres sueltos.** Del código `msg_svc.delete_message(...)`
   guardaba sólo `delete_message` y luego buscaba *ese nombre* por el módulo,
   quedándose con el primer objeto que tuviera uno igual. En un proyecto con
   varios `delete_message`, eso resuelve a **otra función** y la comprobación
   real nunca se mira. Ahora sigue el camino entero.
2. **Miraba un solo salto.** El patrón de aquí es endpoint → servicio →
   ayudante, y la comprobación vive en el tercero la mitad de las veces.
3. **No conocía dos idiomas que este proyecto usa a diario.** La propiedad
   escrita como `fila.user_id == user.id` —cuando el servicio llama `user` a su
   parámetro, como medio `app/services/collaboration/`— y el acotado por
   organización `organization_id=getattr(current_user, "organization_id", None)`,
   que el propio docstring del test **ya nombraba como control válido**.

Ejemplo concreto de lo que se estaba contando mal: `delete_message` comprueba
organización, propiedad del mensaje y rol, y responde 403. Estaba en la lista de
«sin control».

Cada ampliación se añadió **después de leer el código que la justifica**, nunca
para poner el test en verde — que es exactamente el vicio que este test tenía.

### Lo que queda de verdad: 24 rutas

Las 24 se comprobaron a mano: no tienen guarda de rol, ni comprobación de
propiedad, ni acotado explícito por organización en ninguno de los dos saltos.
Todas son `DELETE` de objetos de negocio de la organización —clientes, planes de
capacidad, activos, cambios, plantillas, claves de API, dependencias de tarea—.

El filtrado automático de `TenantSession` impide que un cliente toque los de
otro. Lo que **no** hay es control de quién, dentro de la misma organización,
puede borrarlos: hoy puede cualquier empleado.

Están registradas en `ABAC_UNICO_CONTROL_CONOCIDAS` con trinquete de dos
direcciones —una ruta nueva en esa situación rompe el test, y una que se arregle
y no se quite de la lista, también—, validado rompiéndolo por los dos lados.

**La 25.ª ya está arreglada, y era la única que no necesitaba decisión de
nadie:** `DELETE /sd/rca/templates/{id}` dice «(admin)» en su propio resumen
desde que se escribió, y no tenía guarda. Ahora la tiene. No es una política
nueva: es la que ya estaba escrita, aplicada.

> **Las 24 restantes son deuda medida, no una exención.** Cada una necesita una
> decisión de producto —¿quién puede borrar un cliente, un plan de capacidad, un
> activo?— y no se arreglan en un barrido. Aplicar `require_any_manager` a las
> veinticuatro de golpe sería rápido y sería una ñapa: restringiría flujos
> legítimos sin que nadie lo haya decidido. Es lo primero que hay que mirar de
> lo que queda abierto, y la decisión no es del que refactoriza.

> **Cerrado en §3.trigies: quedan 1 de 24.** Se miraron las veinticuatro una a
> una. **Siete no tenían el problema** —el control existía y el detector no
> sabía leerlo—, **dieciséis llevan ya una guarda con el motivo escrito al
> lado**, y **una no se puede guardar porque no hace nada**. El párrafo de
> arriba sigue teniendo razón en lo que decía: la ñapa habría sido el barrido
> uniforme, y por eso hay cuatro decisiones distintas y no una.

### Un test que sólo pasaba según el orden

`tests/conftest.py` ponía las variables de entorno **después** de
`from app.db.session import TenantSession`, que arrastra `app.core.config` y
construye `settings` con los valores que hubiera **antes**. Consecuencia:
`test_scim_user_provisioning` fallaba —`SCIM_BEARER_TOKEN` vacío— salvo que algo
anterior en la suite hubiera dejado el valor puesto. Un test que depende del
orden no prueba lo que dice probar. El bloque va ahora antes del primer import
de `app`, que es el único sitio donde sirve.

### Y una regresión mía, cazada por un guardián que ya existía

La suite completa acabó con **un fallo**, y era mío. Al sacar el registro de
fallo del trabajo de auto-resolución a su propia función, el `db.rollback()` se
fue con ella — y `tests/test_commit_rollback.py` lo busca **en el cuerpo del
manejador de excepciones, por AST, sin seguir las llamadas**. Señaló el sitio
con fichero y línea:

```
app/api/v1/endpoints/service_desk/ai_auto_resolution.py:429
```

Lo relevante no es el despiste, es **que el guardián tiene razón y su
conservadurismo es el correcto**. El `rollback()` tiene que quedar a la vista en
el manejador: es lo que impide que un fallo de base deje la sesión abortada y
que el `commit()` siguiente reviente con `PendingRollbackError` tapando el error
real —el defecto de 2026-08 que ese test existe para que no vuelva—. Esconderlo
tras una llamada lo deja invisible para el guardián, que es exactamente como ese
defecto volvió cinco veces antes de que el test existiera.

Así que el `rollback()` vuelve al manejador, con el motivo escrito al lado, y el
ayudante deja de deshacer: hay uno solo y está donde se lee.

> Conviene decirlo tal cual: en esta jornada **dos guardianes fallaron por no
> medir** (§3.octovicies) y **uno funcionó exactamente como debía** contra el
> código que yo acababa de escribir. La diferencia entre unos y otro es que este
> comprueba una propiedad sintáctica que no se puede satisfacer por accidente.

### Tests nuevos donde no había ninguno

`tests/test_ask_the_data_sql_policy.py` — **17 casos**. `validate_sql` es lo
único que separa el SQL que escribe un modelo de lenguaje, a partir de texto
libre del usuario, de la base de datos. **No tenía ni un test.** Al
refactorizarla, la única forma de saber si algo cambiaba fue compararla a mano
con la versión anterior sobre 16 casos; esa comparación queda ahora escrita.
Cubre lo que de verdad importa: que el filtro por organización se **inyecta** y
no se confía en el que el modelo haya podido escribir, y que va antes del
`GROUP BY` en las consultas agregadas.

---

## 3.novovicies La suite tardaba preparándose, no ejecutando

**De ~40 minutos a 8.** Y el diagnóstico es más útil que el número.

### Lo que costaba cada test antes de empezar el test

| | por test | × 3818 tests |
|---|---|---|
| Crear y destruir **392 tablas** | 0,836 s | **53 min** |
| **Cuatro** hashes bcrypt de la misma contraseña | 1,190 s | **75 min** |

Ciento veintiocho minutos de CPU montando el escenario. Los tests en sí eran la
parte pequeña, y ninguna optimización de paralelismo iba a arreglar eso.

La fixture `db` es `autouse` y de ámbito de función, así que **todos** los tests
pagaban las dos cosas, tocaran la base o no.

### Los dos arreglos, y lo que deliberadamente NO se hizo

- **El esquema se crea una vez** y entre tests se vacían las filas. Vaciar las
  392 tablas cuesta 0,042 s frente a 0,836 s — veinte veces menos— y deja la
  base igual de limpia. Se vacía **al principio y no al final**: si un test se
  interrumpe a medias, el siguiente sigue empezando limpio.
- **El hash se calcula una vez.** Los cuatro sitios cifraban la *misma* cadena.
  Que los usuarios de prueba compartan hash no cambia nada —sigue siendo un
  bcrypt válido de esa contraseña— y ningún test depende de lo contrario.
- De paso, fuera tres `print` que sacaban la contraseña de prueba y los hashes
  por pantalla en cada test.

**Lo que NO se hizo, y es lo que más se tienta:** bajar las rondas de bcrypt en
tests. Eso habría sido más rápido todavía y habría cambiado el comportamiento de
lo que se está probando. El coste del hashing es parte del sistema; lo que
sobraba era repetirlo cuatro veces por test.

### Y rompió 1857 tests antes de funcionar

Dos tests hacen `DROP TABLE IF EXISTS dashboard_comments` **a propósito**, para
ejercitar el respaldo a JSON de `bi_collaboration_service`. Con `create_all` por
test la tabla se recreaba sola; vaciando, no. Todo lo que iba detrás moría en el
`setup` con «no such table»: **679 errores en un cuarto de la suite y 1178 en
otro**.

> **Lo cazó la suite completa, y sólo podía cazarlo ella.** Los 52 tests
> dirigidos que se corrieron antes pasaron sin un rasguño: el fallo únicamente
> aparece cuando un test se ejecuta **después** de otro concreto. Es el caso
> exacto donde la verificación dirigida no sirve — un cambio en `conftest.py`
> cambia el suelo que pisan los 3818— y donde ahorrarse la pasada completa
> habría metido la rotura entera en `main`.

El arreglo es preciso y barato: antes de vaciar se mira qué tablas existen —1,1
ms, 0,1 minutos sobre toda la suite— y se recrean sólo las que falten, que el
99,9 % de las veces son cero.

### Cómo se corre ahora

Cuatro procesos `pytest` **independientes**, un cuarto de los ficheros cada uno,
repartidos alternos. No `xdist`: sus trabajadores se cuelgan de forma
intermitente en esta máquina (ver la advertencia de entorno de la cabecera), y
cuatro procesos que no se hablan entre sí no tienen ese modo de fallo. El
aislamiento no se pierde — `conftest.py` ya monta una SQLite en memoria por
proceso, que es lo que hace `xdist` por dentro.

Cada proceso escribe su propio registro, así que el avance se ve mientras
ocurre y un cuelgue se localiza en el cuarto que sea.

**Medido:** 3802 passed, 19 skipped, 1 xfailed, **0 fallos**, en 8 minutos de
reloj (6:07 el cuarto más rápido, 7:52 el más lento).

---

## 3.trigies Las 24 rutas sin control, una a una

**De 24 a 1.** Y el reparto importa más que el número, porque las tres suertes
que corrieron son distintas.

| | rutas | qué eran |
|---|---|---|
| Falsos positivos | **7** | el control estaba; el detector no sabía leerlo |
| Guarda aplicada | **16** | no lo tenían; ahora sí, con el motivo al lado |
| Sin arreglo posible | **1** | el endpoint no hace nada que proteger |

### Los siete que ya estaban acotados, y los cuatro idiomas que faltaban

Ninguno se «arregló»: se leyó el código y resultó que el control estaba escrito
de una forma que la expresión regular no contemplaba. Cada hueco está tapado en
el detector, con el ejemplo real que lo destapó:

- **`SavedFilter.created_by == user_id`** — propiedad, con otro nombre de
  columna. Ampliar la lista de nombres a secas habría sido demasiado laxo
  (`Task.assignee_id == assignee_id` es un filtro de búsqueda, no una
  autorización), así que `_acota_por_propiedad` exige **las dos mitades**: que
  el endpoint entregue la identidad de quien llama y que aguas abajo se compare
  contra una columna de propiedad. Aclara 5 rutas.
- **`run_in_threadpool(svc.abortar, uid, current_user)`** — para el AST la
  única llamada ahí es `run_in_threadpool`; `svc.abortar`, que es quien
  comprueba `meta.get("user_id") == user.id`, es un *argumento* y nunca se
  leía. `TRAMPOLINES` sigue las funciones que se pasan a los tres nombres que
  de verdad las ejecutan. Aclara `DELETE /collaboration/tus/{uid}`.
- **`AppSetting.key == f"{_TEMPLATE_KEY_PREFIX}{user_id}"`** — no hay columna
  de propiedad que comparar: el id del usuario **es parte de la clave**, así
  que nadie puede nombrar la fila de otro. Aclara `DELETE
  /reports/templates/{id}`.
- **`DashboardWidget.user_id == current_user_id`** — el parámetro se llama
  `current_user_id` y la alternancia se quedaba en `user_id`. Aclara `DELETE
  /dashboard-widgets/reset`.

### Las dieciséis: cuatro decisiones, no un barrido

El criterio, escrito para que se pueda discutir: **borrar no puede ser más
fácil que crear**. Aplicado da cuatro respuestas distintas, y ninguna es
`require_any_manager` por defecto:

| decisión | rutas | por qué |
|---|---|---|
| La misma guarda que crear | 2 (ALM) | `POST /alm/licenses` y `POST .../installs` ya exigen gestor: revocar con el mismo rol no atrapa a nadie |
| Gestor | 9 | capacidad, clientes, activos, cambios: operaciones de gestión por naturaleza |
| PM o admin | 3 | dependencias y epics: estructura de proyecto, coherente con `POST /epics/{id}/dependencies` |
| Sólo excluir subcontratista | 2 | vínculos de ticket y etiquetas de wiki |
| Propiedad, no rol | 1 | `esign` |

Las dos últimas filas son las que un barrido habría estropeado:

- **Vínculos entre tickets y etiquetas de wiki.** Crear está abierto a
  cualquiera y quitar es la operación inversa exacta, reversible en un clic.
  Restringir sólo el quitar dejaría vínculos y etiquetas puestos por error que
  nadie salvo un PM podría limpiar. Se excluye al subcontratista y ya.
- **`DELETE /esign/{id}`, anular una solicitud de firma.** Aquí
  `require_any_manager` es justo lo cómodo y lo equivocado: `POST /esign` está
  abierto a cualquier usuario, así que exigir rol de gestión para anular
  dejaría al propio solicitante atrapado con una petición enviada por error.
  El control correcto es el de propiedad —`created_by_id`— con los gestores por
  encima, y va **después del 404**, para que quien no puede anularla tampoco
  pueda averiguar por la respuesta si existe.

### La que no se arregla: `DELETE /marketplace/uninstall`

No desinstala nada. Su cuerpo entero es `return APIResponse.ok(data={"result":
"ok"})`. Y no es un caso aislado: `POST /install` tampoco instala y
`GET /instances` devuelve siempre la lista vacía. **El módulo marketplace es
una fachada.**

Ponerle `require_admin` habría puesto el test en verde en diez segundos. Sería
teatro: protege un no-op y deja a la siguiente auditoría leyendo una guarda
donde no hay funcionalidad. Se queda en `ABAC_UNICO_CONTROL_CONOCIDAS` con el
motivo escrito en el propio endpoint, y se guardará el día que haga algo.

### El guardián volvió a satisfacerse solo — y esta vez con mi prosa

Al documentar **por qué** `uninstall_integration` no lleva guarda, el docstring
decía la frase «colgarle un `require_admin` haría pasar el test».

Y la hizo pasar. `SERVICE_AUTHZ_SIGNALS` busca `require_` sobre el fuente en
crudo, sin distinguir código de prosa.

> Es la misma familia que el `enforce_abac` satisfaciéndose a sí mismo de
> §3.octovicies, y era peor de lo que parece: valía para **cualquier**
> endpoint. Bastaba un comentario que nombrase `is_superadmin`, `require_admin`
> o un 403 para que el barrido lo diera por protegido. Cualquiera podía
> silenciar este test escribiendo un comentario.

Arreglado en la raíz, no reescribiendo el docstring: `_sin_prosa` blanquea
comentarios y docstrings **en su sitio** —sin recomponer el fuente a partir de
los tokens, que rompe la adyacencia y hace que `enforce_abac(` deje de
encontrarse— y deja las cadenas normales, que sí son código y hacen falta para
reconocer dos de los cuatro idiomas de arriba.

**Lo cazó la segunda regla del trinquete**, la que obliga a sacar de la lista lo
que ya no aparece. Sin esa regla el arreglo habría entrado en verde y el
detector se habría quedado ciego para siempre.

### Validado rompiéndolo, por los dos lados

- Quitar la guarda de `delete_capacity_plan` → el test la señala como ruta
  nueva sin control.
- Poner un comentario que menciona `require_admin`, `is_superadmin` y un 403 en
  un endpoint sin guarda → **sigue** señalándolo. La prosa ya no cuenta.

### Tres hallazgos que salieron de paso, y son más anchos que las 24

1. **Crear está tan sin guarda como borrar.** El detector sólo miraba rutas que
   llaman a `enforce_abac`, y eso es casi todo `DELETE`. De las 15 rutas de
   escritura de `clients.py`, **ninguna** tenía control de rol; en
   `service_desk` la mayoría de los `POST` tampoco. El hallazgo real no son 24
   borrados: es que el control de rol está puesto a parches en toda la capa API.
2. **Dos rutas públicas para una sola operación.** `DELETE
   /tasks/dependencies/{dep_id}` y `DELETE /task-dependencies/{dep_id}` hacen
   lo mismo desde dos routers distintos. Llevan la misma guarda a propósito —lo
   que no puede pasar es que una sea la puerta de atrás de la otra—, pero sobra
   una.
3. **Sólo 2 de las 16 rutas tenían algún test.** Las guardas nuevas se
   verificaron con la suite completa y con las dos roturas deliberadas de
   arriba; las catorce restantes siguen sin cobertura propia, que es
   probablemente por lo que nadie notó que no tenían control.

---

## 3.untrigies Los tres idiomas al 100 % y pantallas sólo en castellano

Las dos cosas son verdad a la vez, y por eso hacía falta un cuarto medidor.

`check_i18n_coverage.mjs`, `check_i18n.mjs` y `check_i18n_no_new_debt.mjs`
comparan los diccionarios entre sí: cuántas claves tiene `es` y cuántas de esas
están en `en` y en `zh`. Los tres dan 100 %, y no mienten.

**Pero miden el diccionario, no las pantallas.** Una cadena escrita directamente
en el JSX —`<h2>Resumen del proyecto</h2>`— no tiene clave. Al no tener clave no
le falta a ningún idioma, así que los tres gates la dan por buena y el 100 %
convive con pantallas enteras que sólo existen en castellano.

### Cuánto, medido de verdad

**1.852 cadenas en 134 ficheros**, el 65 % de ellas en `src/pages`. Las peores:
`SettingsPageSections.tsx` con 113, `PerformanceReviewsPage.tsx` con 57,
`DocumentsPage.tsx` con 50.

> La primera medición se hizo con expresiones regulares y dio **1.325**. La
> buena es la del AST: la regex no veía el texto que ocupa varias líneas —que es
> la mitad de los títulos y descripciones largas— ni distinguía un `>` de
> comparación de una etiqueta que se cierra. Se deja dicho para que nadie lea
> una mejora de 527 donde sólo hubo un instrumento mejor.

### Tres piezas, no una

- **`check_i18n_literales.mjs`** — el gate. Recorre el AST de TypeScript, no el
  texto, y cuenta nodos `JsxText` y atributos visibles (`placeholder`, `title`,
  `label`, `aria-label`, `alt`) con castellano dentro. Trinquete de dos
  direcciones, como los demás de este repo. Validado rompiéndolo: un `<span>`
  castellano nuevo lo pone en rojo.
- **`i18n_extraer_literales.mjs`** — la herramienta para bajarlo. Edita por
  posiciones exactas del AST, de atrás hacia delante para que los
  desplazamientos no se muevan, y vuelca las claves castellanas. **No inventa
  traducciones**: inglés y chino se escriben a mano, que es trabajo de idioma.
- **`i18n_insertar_modulo.mjs`** — mete el módulo en los tres ficheros de golpe
  y **falla si ya existe en alguno**. Insertar a mano en tres sitios de 4.000
  líneas es exactamente como se llegó al defecto que encontró el gate de
  duplicados: un módulo declarado dos veces, donde JavaScript se queda con el
  último y descarta en silencio 204 traducciones ya escritas.

### Dónde va el hook, que es la parte que se rompe sola

`t` sale de `useAppLang()`, que es un hook de React: sólo puede llamarse en el
cuerpo del componente. El literal, en cambio, casi siempre está dentro de un
`.map(...)` o de un `renderX` anidado. Insertar el hook en la función que
envuelve al literal lo dejaría **dentro del callback** — ilegal, y de las que
funcionan hasta que la lista se queda vacía. Por eso la herramienta busca la
función de **primer nivel del módulo**, que es el componente, y ahí lo pone.

### Cerrado: 1.852 → 0

Ciento treinta y cuatro ficheros, en catorce tandas, cada una con su typecheck
estricto y sus 92 tests de frontend antes de pasar a la siguiente.

**Los dos últimos no eran una pantalla más.** `ErrorBoundary` y `RouteBoundary`
son componentes de **clase** —lo exige React para capturar errores de render—,
así que no pueden llamar a `useAppLang()`. Y aunque pudieran, no deberían: un
boundary se pinta precisamente cuando el árbol de arriba ha fallado, y si lo que
falló fue el proveedor de idioma, la pantalla de último recurso fallaría
también. `traducirSinHook` lee el idioma de `localStorage`: sin contexto de
React, y por tanto sin poder arrastrar al boundary consigo.

### El tercer hallazgo: 174 claves que nadie declaró

Salió al terminar, contando qué claves pedía el código y cuáles existían.

`t('tasks.add_comment')` no deja la pantalla en blanco, que sería evidente.
`resolveTranslation` tiene un último recurso que **humaniza la clave**:

```
t('tasks.add_comment')               ->  "Add comment"
t('tasks.tab_details')               ->  "Tab details"
t('settings.empty_templates_title')  ->  "Empty templates title"
```

Un usuario español lee texto inventado en inglés, con aspecto de estar bien.
**Nadie lo reporta como «falta la traducción» porque no parece que falte nada.**

> **Y ninguno de los cuatro gates podía verlo, por construcción.** No está en
> `es`, así que a `en` y a `zh` no les falta —cobertura 100 %—; y el JSX sí pasa
> por `t()`, así que tampoco es un literal. Es el hueco exacto entre los dos
> tipos de medida que había.

Las 174 son **todas anteriores** a este trabajo. Una de ellas lo explica bien:
`bi_project_detail` estaba declarada **dentro de `alm`** en los tres idiomas, y
como `t()` parte por el primer punto, su ruta real era
`alm.bi_project_detail.subtitle`: inalcanzable. El valor estaba escrito y era
correcto; lo único mal era el sitio.

`check_i18n_claves_sin_definir.mjs` lo vigila, por AST y no por texto —el
docstring de `AppLangContext` documenta la API con `t('module.key')`, y un grep
ingenuo lo denuncia como clave rota—. Validado rompiéndolo.

### Cuatro defectos de la herramienta, cada uno cazado por un guardián distinto

Vale la pena la lista, porque ninguno se encontró leyendo el código:

| qué | lo cazó |
|---|---|
| Hook insertado donde `t` ya significaba otra cosa (`.map(t => …)`) | typecheck estricto |
| `useAppT` insertado en `renderBlocks`, que **no** es un componente | ESLint, regla de hooks |
| Segundo `gantt:` al final de `en.mjs`, que lo declara anidado a 14 espacios | el gate de duplicados, en el mismo minuto: 81 traducciones descartadas |
| `Pagination` y `TimerWidget` renderizados sin proveedor de idioma | los 92 tests de frontend |

El de `renderBlocks` es el que más enseña: la herramienta trataba como
componente toda función de primer nivel. React usa la **mayúscula inicial** para
distinguirlos, y esa es ahora la regla; las funciones que devuelven JSX sin ser
componentes se dejan sin tocar y se listan, porque el arreglo correcto —pasarles
`t` por parámetro— lo decide quien lee el código.

Y el de los tests merece decirse: se arregló montando el contexto **en el
test**, no relajando la guarda de `useAppLang`. Esa guarda existe para impedir
que alguien use la traducción fuera del árbol donde vive; debilitarla para poner
un test en verde habría sido cambiar el producto para no cambiar la prueba.

### Primera pantalla, y lo que costó

`PortalUsersTab.tsx`: 31 literales, 28 claves —los textos repetidos comparten
clave a propósito: «Permisos en el portal» salía dos veces, y traducirla dos
veces es un sitio donde desincronizarse—. `1.852 → 1.821`, typecheck estricto en
cero y ESLint sin errores. Con `SubcontractorsPage`, `OKRsPage`, `ChangesPage`
y `SprintsPage` detrás, **1.721**.

De paso sale un defecto pequeño: el `placeholder` decía «Nueva contrasena», sin
eñe, mientras la etiqueta de al lado decía «Nueva contraseña». Al pasar por una
clave hay un único texto y deja de poder divergir.

---

## 3.duotrigies Casi la mitad de la API escribía sin preguntar quién eras

Esto salió de cerrar las 24 rutas `DELETE` de §3.trigies. El detector de ABAC
sólo mira rutas que llaman a `enforce_abac`, y eso es casi todo `DELETE`; al
contar **todas** las de escritura apareció el tamaño real:

| | antes | ahora |
|---|---|---|
| Rutas de escritura **con** guarda de rol | 603 | **929** |
| Rutas de escritura **sin** ninguna | **563** | 0 |
| Exentas, con motivo comprobado | — | 115 |

`TenantSession` seguía impidiendo el acceso entre organizaciones. Lo que
faltaba era quién, **dentro** de la misma empresa, puede hacer cada cosa.

### Lo que NO se hizo, que es la mitad del trabajo

Poner `require_any_manager` a las 563 habría tardado diez minutos y habría
dejado el producto inservible: imputar horas, abrir un ticket, comentar una
tarea o editar el perfil propio habrían pasado a exigir rol de gestión.

La decisión se tomó con **cinco reglas en orden**, y el orden es el argumento:

1. **Otra superficie de autenticación** → fuera. El portal de cliente
   (`get_current_client`), las API key y los webhooks de proveedor no tienen
   usuario interno: un cliente no tiene rol de empleado y Twilio no tiene rol.
2. **Dominios sensibles** → `require_admin` siempre. Aquí hay un detalle que
   importa: `DELETE /abac/policies/{id}` salía como «acotada al usuario» porque
   el servicio comprueba `created_by`. Para una **política de permisos** eso
   significa «quien la creó puede borrarla», que es demasiado laxo para el
   motor que gobierna los accesos de todos.
3. **Acotada al propio usuario** → exenta. Reutiliza `_acota_por_propiedad`, el
   comprobador ya validado de `test_abac_coverage`.
4. **La guarda que usan sus hermanas** en el mismo fichero. Evidencia del
   repositorio, no gusto de quien refactoriza.
5. **Tabla por dominio** para los ficheros sin ninguna hermana guardada.

Con dos anulaciones que van **antes** de la regla 4, porque la forma de la ruta
dice lo que hace mejor que el fichero donde vive: lo que huele a configuración
(`/config`, `/credentials`, `/providers`) sube a `require_admin`, y lo que huele
a trabajo diario (`/comments`, `/values/`, `/suggest/`, `/analyze`) baja a
`require_internal_user`.

**Y una tabla de excepciones revisadas a mano**, que salió de leer las 109
decisiones restrictivas una por una. El caso que la retrata: `POST /sd/tickets`
salía `any_manager` porque `tickets.py` tiene `merge`, `split` y `auto-assign`
con esa guarda. Abrir un ticket es la acción central de un service desk; pedir
rol de gestión para eso no es endurecer nada.

El reparto final no se parece a un barrido:

| guarda | rutas |
|---|---|
| `require_internal_user` (sólo excluye al subcontratado) | 172 |
| `require_admin` (configuración, credenciales, gobierno) | 127 |
| `require_any_manager` | 53 |
| `require_admin_or_pm` | 19 |
| `require_admin_or_hr` | 8 |

### Las 32 pruebas que corrigieron la primera pasada

La primera aplicación puso 372 guardas y dejó **32 tests en rojo**. Todos
señalaban lo mismo, y con sus propios nombres:

```
test_un_empleado_puede_editar_sus_propios_datos_de_perfil
test_user_can_create_own_plan
test_manager_can_create_plan_for_direct_report
```

Rutas de **autoservicio** restringidas de más: editar el perfil propio, crear
el plan de desarrollo propio, presentar algo a aprobación, decidir como
aprobador designado. En todas ellas el control existe y vive **dentro** del
endpoint —«¿es tu perfil?», «¿eres el aprobador?»—, que es justo lo que un
barrido no puede ver.

> **Ahí el test tiene razón y la guarda no**, y conviene decirlo tal cual: la
> suite no fue un trámite al final, fue el instrumento que corrigió la
> decisión. De esos 32 fallos salió `EXENTAS_REVISADAS`, con las 21 rutas y el
> motivo de cada una.

Dos las decidió el test por otra vía: `POST /developer/apps` y `POST /forms`
llevaban `require_admin` por ser credenciales OAuth y una puerta pública, pero
sus tests usan `pm_token`. La audiencia prevista estaba escrita; la guarda baja
a `require_admin_or_pm`.

### Cuatro defectos del aplicador, cada uno con su síntoma

Editar 360 firmas a máquina tiene su propia lista:

| qué | cómo se vio |
|---|---|
| Firma de una sola línea partida sin coma | 105 errores de sintaxis de ruff |
| `_` como nombre, donde el endpoint ya tenía un `_` | «Duplicate parameter» |
| La misma función registrada en v1 **y** v2, parcheada dos veces | «Duplicate parameter», 17 de ellas |
| El import nuevo dentro de un `from … import (` multilínea | el fichero dejaba de parsear |

El último es el mismo fallo que ya costó un `en.mjs` roto en la tanda de
traducción, con otra sintaxis: «la última línea que empieza por `import`» es la
**apertura** de un import multilínea. Se arregla igual, preguntando al AST por
el final del último import y no al texto por su principio.

### El guardián

`tests/test_guardas_de_rol.py`, cuatro reglas:

1. Ninguna ruta de escritura sin guarda **y sin motivo**.
2. Las exenciones escritas a mano siguen correspondiendo a una ruta real — una
   entrada que sobra convierte la lista en historia en vez de descripción.
3. El reparto de exenciones automáticas, en su número medido, con trinquete de
   dos direcciones.
4. Las 929 guardas no retroceden.

Validado rompiéndolo: quitar **una** guarda de `clients.py` pone dos de las
cuatro en rojo.

---

## 3.tertrigies Probar que la guarda deniega, no que está escrita

`test_guardas_de_rol.py` comprueba una propiedad **sintáctica**: que toda ruta
de escritura lleva guarda o una exención con motivo. Lee el código fuente. No
dice nada sobre si el 403 llega.

Y en este repositorio eso ya ha fallado dos veces, de formas distintas: el
middleware ABAC que nunca se ejecutaba (hallazgo 1) y `enforce_abac`, que es
fail-open y no comprueba nada sin políticas activas (§3.octovicies). Escribir el
nombre de la dependencia no demuestra que la puerta cierre.

`test_guardas_deniegan.py` lo demuestra: **para cada uno de los 979 pares
(método, ruta) con guarda, lanza la petición con un rol que esa guarda tiene que
rechazar y exige un 403.** Las 979 lo dan.

### El rol con el que se sondea cada guarda

| guarda | se sondea con | por qué |
|---|---|---|
| `require_admin`, `_or_pm`, `_or_hr`, `any_manager` | empleado | ninguno de esos conjuntos incluye a `employee` |
| `require_internal_user` | **subcontratado** | es el único rol que excluye |
| `require_superadmin` | admin de tenant | `admin` NO es superadmin |

Hizo falta sembrar un usuario subcontratado en `conftest.py`. No es un detalle:
sin él, la única sonda para `require_internal_user` era un empleado, que la
guarda deja pasar — y un test que nunca puede ver el 403 no prueba nada.

### Dos decisiones que costaron una reescritura

**Una sola prueba, no 979 parametrizadas.** La fixture `db` es `autouse` y de
ámbito de función: parametrizar reconstruía el escenario una vez por ruta y el
fichero solo tardaba más de diez minutos — habría duplicado la suite entera por
sí mismo (§3.novovicies). Recorriéndolas en un bucle se paga una vez: **31
segundos**. Se pierde el detalle por caso del informe de pytest y se recupera
con creces en el mensaje, que saca todos los fallos juntos.

**Se manda el cuerpo vacío, y eso hay que comprobarlo.** En FastAPI las
dependencias se resuelven antes de validar el cuerpo, así que una que lanza
corta ahí. Comprobado sobre `POST /clients`, que tiene cuerpo obligatorio: con
`{}` responde 403, no 422. Hay un test dedicado sólo a ese supuesto, porque si
algún día cambiara, los 979 sondeos estarían midiendo otra cosa sin avisar.

### Y un agujero del propio test, encontrado al romperlo

Se validó comentando una guarda de `clients.py` — «escrita pero no corre», que
es justo el caso que este fichero existe para cazar. **Y pasó en verde.**

Porque al comentarla, `_sin_prosa` deja de verla y la ruta **desaparece de la
lista a sondear** en vez de fallar: el bucle pasa porque ya no la mira. El
umbral era `>= 929` y tenía holgura de sobra.

Se cierra clavando el número exacto (979 pares, que no son las 929 funciones de
`test_guardas_de_rol.py` porque `main.py` monta los routers en v1 y v2). Y
conviene decir el reparto de papeles, porque no es redundancia: **quitar una
guarda lo caza el guardián sintáctico** —comprobado, pone 2 de sus 4 en rojo—,
y lo que caza éste es que la lista a sondear se quede coja.

---

## 3.quattuortrigies La traducción, por dentro

Cerrado el «0 literales fuera de `t()`», quedaba la pregunta de si lo traducido
está bien. La revisión por un hablante nativo no la puedo hacer; lo que sí se
puede es comprobar por máquina tres cosas, y las tres dieron defectos reales.

### Variables `{x}` que no cuadraban: cuatro, y ninguna era cosmética

`t('clave', { total, active })` sustituye `{total}` y `{active}` en el texto del
idioma activo. Si la traducción no lleva las mismas variables pasa una de dos
cosas, y ninguna avisa: sobran y el usuario lee `{count}` tal cual, o faltan y
el dato no aparece **sin que la frase deje de tener sentido** — que es
exactamente lo que hace que nadie lo reporte.

| clave | qué pasaba |
|---|---|
| `projects.subtitle` | el código pasa `{total} {active} {atRisk}`; inglés y chino tenían una frase genérica **sin las cifras**. La misma pantalla daba menos información según el idioma |
| `milestone_billing.subtitle` | el valor **castellano** decía «Team capacity projection — {weeks} weeks»: texto en inglés, y del módulo de capacidad |
| `m365.subtitle` | igual: «{total} people · Reporting structure · Approval chains», del organigrama |
| `offline_indicator.pending_label` | `{count} pendiente{s}` esperaba que alguien pasara `s` valiendo `""` o `"s"`. No la llama nadie, así que de usarse mostraría «3 pendiente{s}» |

> Los dos del medio son lo interesante: **el descuadre de variables no era el
> defecto, era el síntoma** que destapó dos valores copiados de otro módulo en
> el diccionario castellano. Inglés y chino tenían el texto correcto; sólo el
> castellano estaba mal.

`check_i18n_variables.mjs` lo vigila. Validado rompiéndolo.

### 35 claves duplicadas que creé yo

Al comparar términos por módulo salió que el mismo castellano tenía dos chinos
distintos: «Sin páginas» era 无页面 y 暂无页面 según el sitio.

La causa es un defecto de la extracción de §3.untrigies: genera la clave a
partir del texto, y el insertor sólo saltaba las que ya existían **con ese
nombre**. Cuando el módulo ya tenía ese texto con otro nombre —`wiki.no_pages`—
se creaba `wiki.sin_paginas` con el mismo castellano, y cada una se tradujo por
su cuenta.

El arreglo no es igualar las dos traducciones: es **quedarse con la clave que ya
existía, apuntar el código a ella y borrar la nueva**. 38 usos repuntados, 104
entradas fuera de los tres diccionarios. Menos claves, y la divergencia deja de
ser posible.

Quedan 114 pares preexistentes con el mismo castellano en el mismo módulo, de
los que sólo **6 divergen en chino y 7 en inglés**. De esos, la mitad es
contexto legítimo y se deja escrito por qué: `alm.vendor_label_web` es el sitio
web del proveedor y `licenses_platform_web` es la plataforma web; en
`service_desk` «Resuelto» es un estado en un sitio y una fecha en otro.

### El inglés mezclaba británico y americano

Medido sobre las 5.711 claves, el británico ganaba en las cuatro familias, así
que el producto habla inglés británico y había una minoría suelta:

| | antes | ahora |
|---|---|---|
| `-ize` / `-ise` | 26 / 38 | **5** / 59 |
| `license` / `licence` | 7 / 23 | **0** / 30 |
| `center` / `centre` | 1 / 10 | **0** / 11 |
| `color` / `colour` | 3 / 5 | **0** / 8 |

Con una lista revisada a mano, **no con un reemplazo ciego**, porque hay
palabras que en británico se escriben igual: `size`, `resize` y `batch size` no
son alternables, y `Authorization flow` es el término de la especificación
OAuth. Los cinco `-ize` que quedan son exactamente esos.

---

## 3.quintrigies El instalador de Windows no llegaba a arrancar

Salió de una pregunta sencilla —«¿puedo lanzar esto desde Windows?»— y la
respuesta honesta era «no, y por dos sitios distintos». Los dos estaban en el
camino **documentado**: `setup.bat`.

### Uno: el sembrado moría al imprimir un «✓»

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u26a0'
```

La consola de Windows arranca en la página de códigos **850** —o 1252—, y el
sembrado tiene **81 `print` con caracteres fuera de ASCII repartidos en 14
ficheros**: los «✓» de cada paso, el «⚠️» que avisa de la contraseña.

No era un adorno que se rompe. El proceso moría a mitad, la transacción se
deshacía y la base quedaba **con cero usuarios**: instalación aparentemente
terminada y sin forma de entrar en la aplicación.

> El arreglo va en la **salida**, no en los 81 `print`: el problema no es el
> texto, es el descriptor. `setup.bat` fija `PYTHONUTF8=1` para todo lo que
> lanza, y `app/db/seed.py` reconfigura `stdout`/`stderr` con
> `errors="replace"` para quien ejecute el módulo a mano. Arreglar print a
> print habría sido perseguir el síntoma catorce veces.

### Dos: `setup.bat` no aplicaba las migraciones. Nunca

Cero apariciones de `alembic` en el fichero. Y no es que el proyecto no las
tenga: **su gemelo de Linux sí lo hace** —`setup.sh` corre `alembic upgrade
head` y aborta si falla, «la aplicación NO se arranca con un esquema a
medias»—, `docker-compose` lo lleva como comando de arranque y el `Makefile`
tiene `make migrate`. El único de los cuatro caminos que se lo saltaba era el de
Windows.

Medido en una máquina real: `clarive.db` no tenía ni tabla `alembic_version`,
le faltaba `imputations.work_type` (revisión 096) y el sembrado moría con
`no such column` a mitad.

Se añade `:apply_migrations` a los **dos** caminos —instalación completa y
«sólo arrancar»—, porque tras un `git pull` el segundo es el que se usa.

### Verificado de punta a punta

Borrando la base y ejecutando `setup.bat start` con el `.env` del repositorio:
Alembic la reconstruye entera hasta la revisión 096, el sembrado termina, y
quedan 9 usuarios y 5 proyectos. Backend en 8000 respondiendo `{"db":"ok"}`,
frontend en 3000 sirviendo, y `POST /api/v1/auth/login` con `admin` devuelve
200.

> Un detalle de la máquina, no del código: Vite escucha en `[::1]:3000`, así que
> `curl http://127.0.0.1:3000` da error de conexión y `http://localhost:3000`
> funciona. Vale la pena saberlo antes de pensar que el frontend no arrancó.

---

## 3.sextrigies La IA sólo se podía configurar con Anthropic

`.env` admitía **una** credencial de IA: `ANTHROPIC_API_KEY`. La aplicación
soporta **ocho** proveedores —anthropic, openai, gemini, deepseek, ollama, groq,
mistral, azure—, así que quien trabajara con cualquier otro no tenía forma de
configurar el despliegue por fichero: o pasaba por la interfaz, o no había IA.

### Lo que ya estaba bien, y conviene decirlo

Al mirarlo de cerca el código estaba mejor de lo que el `.env` sugería: **15 de
17 módulos** ya usan el despachador multi-proveedor, y los dos que parecían
atados a Anthropic no lo estaban del todo. El chat usa `call_ai` —agnóstico— y
Anthropic sólo añade *streaming* nativo token a token; el agente cae a un modo
degradado que **avisa en el primer evento** de que no hay *tool-use* real, en
vez de fallar en silencio. Alguien ya había corregido el mismo desajuste en el
portal de cliente, con un comentario que lo dice: «hardcoded a
ANTHROPIC_API_KEY — engañoso si la empresa usa Gemini/OpenAI/Mistral».

El hueco real era sólo el fichero de entorno.

### El patrón, que ya existía en el proyecto

No se inventa uno nuevo: `app/services/stt/__init__.py` ya resolvía
`organización → global → env` para el motor de voz. Se aplica el mismo a los
proveedores de IA:

```
proveedor de la organización (BD) → proveedor global (BD) → .env
```

> **Y aquí está el matiz que importa, porque «todo lo configurable debe estar en
> `.env`» no es del todo cierto.** Un `.env` es *por despliegue*: un único valor
> para todo el proceso. La configuración de proveedores es **por organización**
> —el modelo tiene `organization_id`—, y un fichero de entorno no puede expresar
> «la empresa A usa Gemini y la B usa OpenAI». La base de datos no sobra. Lo que
> sí tiene que poder hacerse por fichero, y no se podía, es configurar **entero**
> un despliegue de un solo cliente sin abrir la aplicación. Eso es lo que
> resuelve el tercer escalón.

Cuatro variables, agnósticas:

```
AI_PROVIDER=gemini
AI_API_KEY=...
AI_MODEL=gemini-2.0-flash      (opcional)
AI_BASE_URL=...                (sólo Ollama o Azure)
```

`ANTHROPIC_API_KEY` se mantiene como **alias heredado**: sin `AI_PROVIDER`, una
clave ahí resuelve a Anthropic igual que antes. Ningún `.env` existente deja de
funcionar.

### Dos decisiones de implementación

**El proveedor del entorno no hereda de `AIProvider`.** No es una fila, no se
persiste y no debe poder acabar en la sesión por accidente. Lleva los mismos
atributos que el despachador necesita y los contadores en memoria, que se
descartan al acabar la petición. Hay un test que comprueba justo eso.

**La clave del entorno se guarda cifrada en el objeto**, aunque venga en claro
del fichero, porque `call_provider` descifra siempre. Así el camino de llamada
es **el mismo** para un proveedor de base de datos y para uno de entorno: un
solo sitio que descifra, y no dos ramas que puedan divergir.

16 tests cubren los ocho proveedores, el alias heredado, Ollama sin clave, el
proveedor desconocido, la precedencia de la base sobre el entorno y que el
objeto virtual no acabe en la sesión.

---

## 3.duovicies El barrido de duplicación: 31 parejas, cero defectos

La duplicación ha sido **el detector más productivo de toda esta auditoría**, y
hasta ahora se encontraba siempre de casualidad, mirando otra cosa: la copia del
dominio de tareas a la que le faltaba ABAC, los dos marketplaces, los dos
generadores de factura —y el que usaba la interfaz no llevaba el NIF—,
`execute_report` contra su gemela paginada, el `PUT` y el `PATCH` de SCIM
cubriendo campos distintos, las dos copias del sondeo SNMP.

Seis hallazgos por el mismo camino y **nadie había barrido el repositorio
entero buscándolo**. Ahora hay `scripts/audit_funciones_duplicadas.py`.

### Cómo mide, y por qué así

Normaliza cada función a su **esqueleto de AST**: desaparecen los nombres de
variables locales, las constantes y los comentarios; quedan la forma de las
sentencias, los atributos, las llamadas y **los nombres que la función
importa**. Dos copias con las variables renombradas siguen saliendo iguales, que
es justo el caso que un `diff` de texto no ve.

Sólo compara funciones de doce sentencias o más y de tamaño parecido. Por debajo
de eso el parecido no significa nada: cinco líneas de `getattr` con respaldo se
repiten en todas partes y no son una copia, son un idioma.

### Lo que el propio detector me enseñó

**Los nombres importados tienen que contar.** La primera versión los descartaba
y dio como **idénticas** a `metric_tasks_by_status` y `metric_epics_by_status`,
que son correctas: una consulta `Task` y la otra `Epic`. Como este repositorio
importa los modelos **dentro** de la función para evitar ciclos, ambos eran un
`ast.Name` cualquiera y la única diferencia real se perdía en la normalización.
Conservarlos arregla el falso positivo sin romper lo que el detector busca, y
bajó el recuento de **35 parejas a 31**.

### El resultado, que es un negativo y conviene decirlo

**Las 31 parejas se miraron una a una, y ninguna es un defecto.** Cada una
difiere exactamente en lo que debe: los umbrales de `users_at_capacity` contra
`users_underutilized`, el `grant_type` de un intercambio de código OAuth contra
un refresco, `int()` contra `float()`, `Expense` contra `GitPullRequest`.

Dos merecen mención por lo cerca que estuvieron de ser algo:

* **`_tenant_filter_for_model` y `_tenant_where_for_model`** —las dos capas del
  aislamiento— son **idénticas en política**. Sólo cambian el docstring, un
  ajuste de línea y un mensaje de error. Es el sitio donde una divergencia
  costaría más cara, y ya divergió dos veces en esta auditoría (§3.bis,
  §3.vicies), así que comprobarlo tenía valor aunque saliera limpio.
* **`_serie_users_at_capacity` y `_serie_users_underutilized`** llevan a mirar si
  el motor de alertas BI filtra por organización. Filtra: se llama desde
  endpoints con la sesión de la petición, que ya trae contexto, y no hay
  evaluación programada en el `worker` que lo haga sin él. Comprobado, no
  supuesto.

### Y una consolidación que sí hacía falta

`_ticket_category` estaba escrita dos veces —en `alert_correlation_service` y en
`incident_intelligence_service`—, idénticas salvo el nombre, y **las dos llevaban
la misma nota de `FIX:`** explicando el mismo defecto: alguien asumió que
`Ticket` tiene una columna `category` y no la tiene, así que el clustering
reventaba con `AttributeError`.

Que el mismo arreglo esté escrito dos veces es el aviso. Cuando la fuente de la
categoría cambie habrá que acordarse de los dos sitios, y **el que se olvide no
fallará a gritos**: devolverá un discriminador distinto y los grupos saldrán mal.
Ahora vive en `service_desk/ticket_category.py` y los dos servicios la
reexportan con su nombre local, así que ningún sitio de llamada cambia.
Comprobado que los tres nombres son **el mismo objeto**.

Vive en módulo propio y no en uno de los dos servicios a propósito: correlación
de alertas e inteligencia de incidentes son dominios hermanos, y hacer que uno
dependa del otro por un accesor de doce líneas sería peor que la copia.

### Cómo se verificó, y qué NO se pudo verificar

**26 tests en verde** —los dos ficheros que ejercitan los servicios tocados más
los cuatro guardianes estructurales (complejidad, acceso a base en la capa API,
rutas tapadas)—, `ruff` limpio, y comprobado por identidad que los tres nombres
apuntan al **mismo objeto**.

**La suite completa no se pudo ejecutar en esta sesión**, y conviene decirlo en
lugar de omitirlo: `pytest-xdist` se quedaba colgado —los trabajadores arrancan
y no consumen CPU—, tanto con `-n auto` como con `-n 2` sobre un solo fichero, y
en un solo proceso la suite no cabe en ninguna ventana razonable. El cambio de
backend de esta tanda es un módulo nuevo y dos alias en su sitio, así que lo
verificado cubre lo tocado; la próxima tanda debe empezar por una pasada
completa.

### Lo que este barrido no cubre, dicho antes de que se olvide

El umbral de doce sentencias deja fuera a los ayudantes cortos, y ahí hay
**dieciocho** definiciones del par `_get_json`/`_set_json` sobre `AppSetting`
repartidas por los servicios de BI y de Service Desk. Cinco de ellas **no
reciben `organization_id`**, lo que tenía toda la pinta de ser §3.novies otra vez
—las credenciales de e-firma de un cliente guardadas como valor global—.

**No lo es, y se comprobó una por una**: las cinco meten el `org_id` dentro de la
clave (`bi.embed.config.{org_id}`, `sd.capacity.config.{org_id}`,
`sd.reports.presets.{org_id}`…), así que el aislamiento existe; lo consigue el
nombre de la clave en vez de la columna. Funciona, y **depende de que cada sitio
de llamada se acuerde**, que es una garantía más débil que una columna. Queda
anotado como lo que es: deuda de diseño con el comportamiento correcto hoy.

## 3.unvicies Dos críticas por una librería de mapas que nadie usa

El 15 de septiembre, **sin un solo commit de código desde el 9**, el gate
bloqueante `npm audit --audit-level=high` estaba en rojo: 9 avisos, **2 críticos
y 1 alto**. Es exactamente lo que este documento avisaba dos párrafos más
arriba: «`npm audit` cambia sin que nadie toque el código; una frase como "está
a 0" caduca sola». Conviene que quede escrito que la advertencia se cumplió, y
en menos de una semana.

### Qué había

| Severidad | Paquete | Por dónde entra | Arreglo que ofrecía npm |
|---|---|---|---|
| crítico ×2 | `maplibre-gl` ≤ 6.4.0 (bypass del sanitizador, XSS) | `plotly.js` 2.35.3 | `plotly.js@4` — **mayor** |
| alto | `js-yaml` 4.0.0–4.3.1 (CPU sin límite en claves de mezcla) | `eslint` → `@eslint/eslintrc` | sin romper |
| moderado ×3 | `@humanfs/node`, `@vitest/mocker`, `vitest` | herramientas | sin romper |
| moderado ×3 | `echarts` < 6.1.0, `react-router(-dom)` | directas | **mayor** (deuda ya declarada) |

### La medición que cambió la respuesta

La ruta que proponía npm era subir `plotly.js` de 2 a 4: una migración mayor
sobre seis componentes de gráficos. Antes de aceptarla se hizo la pregunta
barata: **¿esta aplicación dibuja algún mapa?**

Un barrido de tipos de traza sobre `src/` devuelve `box`, `violin`, `scatter3d` y
`surface` en plotly — y **ninguna de mapa**. Los otros cuatro tipos que aparecen
en el código (`candlestick`, `funnel`, `gauge`, `heatmap`) los dibuja
`echarts-for-react`, no plotly; se comprobó fichero a fichero, que es la
diferencia entre recortar y romper.

Es decir: `maplibre-gl` viajaba dentro del bundle completo de `plotly.js` sin que
nadie lo llamara. **La vulnerabilidad estaba en código que se servía al
navegador y no se ejecutaba nunca.**

### El arreglo: recortar, no subir de versión

`src/charts/PlotlyCustom.ts` parte de `plotly.js/lib/core` —que no trae ninguna
traza— registra las cuatro que se usan, y exporta el componente con
`createPlotlyComponent`. Los cinco componentes que importaban
`react-plotly.js` pasan a importar ése. Con eso el grafo de módulos deja de
alcanzar `maplibre`, `mapbox` y `geo`.

Dos resultados medidos sobre el build:

* **`vendor-plotly`: 4.633 kB → 1.563 kB** (gzip 510 kB), un **−66 %**. La cifra
  vieja no es una estimación: estaba escrita en el comentario de `CMDBPage.tsx`,
  que por eso ya cargaba la topología en diferido. Ese `lazy` sigue mereciendo la
  pena; simplemente ya no esconde tanto.
* Los **dos críticos desaparecen**.

### Por qué además hace falta un `override`, y por qué es seguro aquí

Un bundle a medida quita el código vulnerable de lo que se sirve, **pero no pone
el gate en verde**: `npm audit` lee el árbol de dependencias, no lo que se
importa. Así que `package.json` fija `overrides: { "maplibre-gl": "^6.9.1" }`,
por encima del rango afectado.

Un `override` así sería temerario con el bundle completo —`plotly.js` 2.x está
escrito contra la API de `maplibre` 4.x—, y es sano **precisamente porque** el
bundle a medida no incluye ninguna traza de mapa: ese código ya no entra en la
compilación. Las dos piezas se sostienen la una a la otra, y por eso van juntas.

### El guardián

`src/charts/__tests__/plotlyCustom.test.ts` falla si cualquier fichero vuelve a
escribir `import ... from 'react-plotly.js'`, y comprueba que el módulo a medida
registra las cuatro trazas y **ninguna de mapa**.

Hace falta porque el arreglo se deshace con una sola línea y **el fallo sería
silencioso en lo que se mira**: el gráfico se vería perfectamente. Lo que
volvería —el peso y la dependencia vulnerable— no se nota en pantalla. Validado
rompiéndolo: se añadió un componente con el import prohibido, el test falló
nombrando el fichero, y se borró.

### Y lo no-rompedor, de paso

`npm audit fix` sin `--force` resolvió el alto (`js-yaml`) y las tres moderadas
de herramientas tocando **sólo el lockfile**: `package.json` no cambia más que
por el `override`. De 9 avisos a 3, y los 3 que quedan son las dos migraciones
mayores que ya estaban declaradas como deuda deliberada.

Verificado: `npm audit --audit-level=high` **en verde**, build `exit 0`, `tsc`
limpio y **91/91** en vitest (27 ficheros, con los dos guardianes nuevos).

## 3.vicies Tres capas de aislamiento y una bandera que sólo respetaba una

Registrar los escuchadores de tenant en la suite (§3.sexdecies) puso **23 tests
en rojo**. Dos eran regresiones mías de esta misma jornada y están al final de
esta sección. De los otros veintiuno, catorce eran del banco de pruebas —filas
sembradas sin organización que ahora nacen con la de la sesión— y **siete
destaparon defectos de producción**. Éstos son.

### El defecto de fondo: el aislamiento son tres capas, no una

`app/db/session.py` monta el aislamiento en tres sitios: `TenantSession.query()`,
`TenantSession.execute()` y el escuchador `do_orm_execute`. La cabecera del
tercero documenta una salida de emergencia —`bypass_tenant_filter`— «para
scripts de migración y trabajos de analítica entre tenants».

**Y de las tres capas sólo la respetaba esa.** Las otras dos —que son justo las
que usa el código normal— la ignoraban. Una bandera documentada que no hace lo
que dice es peor que no tenerla, porque quien la usa cree que ya está protegido.
Ahora la respetan las tres, y se enciende por `sin_filtro_de_tenant(session)`,
un bloque que la devuelve al salir.

De esa suposición —«el filtro es una capa y sé cuál»— salieron los tres defectos
de abajo, escritos por manos distintas y en módulos distintos.

### 1. Mover un usuario de organización devolvía 500, con el cambio ya hecho

```
PATCH /users/{id}  con organization_id de otra organización
  → db.commit()   mueve al usuario
  → db.refresh(user)   no lo encuentra: la sesión sigue en la organización
                       de quien llamó, y la fila ya no está ahí
  → InvalidRequestError: Could not refresh instance '<User>'  →  500
```

**El peor final posible: la operación tuvo efecto y la respuesta dice que no.**
El mismo patrón en el alta —un superadmin dando de alta al primer administrador
de un cliente nuevo—. Y una segunda mitad que no se ve a la primera: las
pertenencias a organizaciones son una relación **perezosa**, así que aunque el
`refresh` funcione, cargarlas al serializar la respuesta las trae otra vez
filtradas y el alta contesta con las organizaciones de quien llama en lugar de
las del usuario creado. Hay que tocarlas dentro del bloque.

### 2. La suscripción push que decía ir «por Core» y no

`_suscripcion_por_endpoint` buscaba la fila por `endpoint` —columna **única
global**— con una consulta de SQLAlchemy Core, y lo explicaba así: «va por Core y
no por el ORM a propósito; el filtro global de tenant sólo actúa sobre sentencias
ORM».

**Falso.** `TenantSession.execute()` intercepta cualquier `Select`, y
`_extract_models_from_select` **resuelve la `Table` de vuelta a su clase mapeada**
por el registro de SQLAlchemy — para eso se escribió. Así que la consulta salía
filtrada, la fila ajena seguía invisible, y **el 500 por violación de unicidad
que ese ayudante existe para evitar seguía ocurriendo en producción**.

Y dos líneas más abajo, el mismo error otra vez: el `UPDATE` que traspasa la fila
colgaba de `db.query(...)`, con un comentario que decía que «el filtro no toca
las sentencias de escritura». Es verdad del escuchador y falso de esa línea:
`query()` añade el `WHERE` y `.update()` lo hereda, así que el traspaso
**actualizaba cero filas en silencio** — y el código auditaba a continuación un
traspaso que no había ocurrido.

**Por qué el test no lo vio, que es lo importante.** El test *sí* activaba el
filtro a mano, y su docstring explicaba muy bien por qué hacía falta. Pero lo
enganchaba sobre una sesión de pruebas que era un `Session` **plano**, y un
`Session` plano no tiene los `override` de `query()`/`execute()`: deja pasar el
Core. Es decir, **el test reproducía media condición de producción y daba por
bueno un arreglo que allí no funcionaba**. Un escenario reproducido a medias no
es un escenario reproducido, y ésta es la moraleja más cara de la jornada.

### 3. Y las dos regresiones mías, que también las cazó la suite

**`GET /pipeline/{opp_id}` tapaba tres rutas.** El endpoint de detalle que se
añadió al cerrar el hallazgo 37 se declaró antes que `/forecast`, `/stages` y
`/stage-configs`, y en FastAPI gana la primera que encaja. Con él cayeron siete
tests de previsión de ingresos y de configuración de etapas. Lo peor no es el
error: es que **el comentario que lo acompañaba decía que iba colocado para no
tapar nada, y citaba §3.g como el defecto que no se repetía**. Se repitió, y
mientras se escribía que no. La lección corregida está en el propio código: el
orden de declaración es **global al fichero**, no local al bloque, así que la
ruta de detalle va la última y no «después de las que me acordaba».

**Y el export de proyectos hacía `db.query()` en la capa API**, que es
exactamente lo que el hallazgo 22 acababa de cerrar a cero. Lo cazó su guardián
de tolerancia cero, en un endpoint escrito en la misma auditoría que lo cerró.
Dice algo bueno del guardián y algo honesto de quien escribe: la disciplina no
se sostiene sola, por eso se automatiza.

## 3.octodecies El hallazgo 18: de «no había medida» a 94 → 80, con trinquete

El 18 llevaba abierto toda la auditoría y la razón no era la falta de ganas:
**no había ninguna medida**. `ruff.toml` selecciona `E, F, W, S, B`, y `C901`
no está entre ellas. Una función podía pasar de 10 a 20 sin que nada dijera
nada, y «complejidad excesiva» era una opinión.

Ahora hay tres cosas que antes no había:

* `scripts/audit_complejidad.py` — la medida. **Llama a ruff** en vez de
  reimplementar McCabe: la definición ya existe y tener dos sería peor que tener
  una. Los otros detectores de esta auditoría son AST puro porque la regla que
  aplican no existía; aquí sí existe, lo que faltaba era que alguien la mirara.
* `tests/test_complejidad_no_empeora.py` — el trinquete, con tres reglas.
* Una línea informativa en `ci_local.sh` con el reparto, para elegir la
  siguiente sin ir a buscarla.

Medido: **94 funciones por encima de 10 → 80; exceso acumulado 253 → 205;
máximo 17 → 16.**

### Catorce funciones fuera, y ninguna por partirla en trozos

Esto es lo que importa del número. Ninguna de las catorce se quitó bajando su
complejidad a base de trocearla: **las catorce escondían un defecto**, y la
complejidad fue el detector, igual que en §3.b y §3.c. El reparto exacto, porque
un «catorce» sin desglosar no se puede comprobar:

**Dos copias literales del dominio de tareas** (§3.novodecies, abajo) —
`bulk_update_tasks` y `cascade_reschedule` de `task_service.py`, que ya existían
en el subpaquete `app/services/tasks/`. En total el módulo duplicaba cuatro
funciones; las otras dos no llegaban al umbral y por eso no cuentan aquí.

**Dos métodos de `TaskService`** —`update` y `bulk_update_dates`— de una clase de
387 líneas, once métodos y **ni un solo sitio de llamada**.

**Una cascada de roles**: la de la actualización masiva de tareas, donde la misma
comprobación de asignatario estaba escrita tres veces, cada una con su
`skipped.append` y su `continue`.

**Tres preámbulos de autenticación de WebSocket**: notificaciones de usuario,
notificaciones de portal y colaboración en documentos tenían el mismo bloque
copiado —ticket de un solo uso, o JWT en la URL si no estamos en producción, y
un cierre distinto por cada forma de fallar—, seis ramas cada uno, dieciocho en
total. Ahora es `_identidad_de_la_conexion`, que devuelve el id **después de
haber cerrado el socket** si no hay: por eso cada WebSocket se queda en dos
líneas en vez de repartir otra vez las mismas ramas. Y de `ws_doc_collab` —17,
la más alta del backend— salió además el bucle de mensajes: no es ciclo de vida
de conexión, es protocolo.

**Dos tablas de comandos de bot**: `slack_inbound_command` y
`teams_inbound_command` tenían la misma cascada `if verb in (...)`. Y **las dos
copias no decían lo mismo**: Slack aceptaba `horas` como sinónimo de `tiempo` y
Teams no, así que un usuario de Teams que escribía «horas 3» recibía la ayuda en
lugar de registrar sus tres horas. El docstring de Teams decía literalmente
«commands identical to the Slack bot». Ahora hay un `_COMANDOS` y las dos
plataformas comparten repertorio; de paso salieron a funciones propias la
verificación de firma de Slack y la del bearer de Teams.

**Cuatro cascadas que son literalmente una tabla**: los operadores de búsqueda
de la mensajería (`from:`, `has:`, `is:`…), las frecuencias de las tareas
recurrentes, el reconocimiento del `User-Agent` y los contadores de la
instantánea horaria de seguridad. En la del `User-Agent` la tabla
además **hace visible una trampa que la cascada escondía**: el orden importa,
porque el `User-Agent` de Edge contiene `chrome/` y el de Chrome contiene
`safari/`. Reordenar por parecer más lógico haría que Edge se reconociera como
Chrome sin que nada fallara a gritos; ahora está escrito encima de la tabla.

### Por qué el trinquete registra cada función y no sólo un total

Porque un total baja partiendo cualquier cosa. `CONOCIDAS` guarda las 80 con su
valor, y las reglas son tres:

1. Una función que **no está en la lista** no puede superar 10 — el código nuevo
   nace por debajo del umbral. Ésta es la que de verdad importa.
2. Una que **sí está** no puede subir de su valor registrado.
3. Si una **mejora**, el test también falla y pide actualizar la lista. A
   propósito: un trinquete que sólo mira hacia arriba deja la foto envejecer, y
   entonces alguien sube de 11 a 16 sin que salte nada.

Validado rompiéndolo: se añadió a `app/` una función de complejidad 12 y el
guardián falló nombrándola, con el mensaje que dice que **no** se arregla
metiéndola en la lista. Después se borró y volvió a pasar.

### Las 80 que quedan, medidas y no supinas

«Son largas pero lineales» es una afirmación, así que se comprobó en vez de
escribirla. Un barrido por AST sobre las 81 de entonces busca la firma de una
tabla de despacho —una cadena `if/elif` de cuatro ramas o más donde **todas** comparan el
mismo operando con `==` o `in`—, que es la forma que tenían las tres cascadas
recién convertidas y la que tenía `apply_filter` cuando se midió lo mismo hace
dos tandas.

**Resultado: 1 de 81.** `_bump_snapshot` en `security_observability.py`, con dos
cadenas de cinco ramas que eligen a qué contador de la instantánea horaria
sumarle uno. Convertida también, y **el barrido repetido sobre las 80 que quedan
devuelve cero**: no hay ninguna escondida.

Esas 80 son funciones largas pero **lineales**: reglas de negocio
encadenadas donde partir por partir mueve el problema de sitio y añade
indirección sin quitar riesgo. Bajarlas es trabajo legítimo y hay que hacerlo;
lo que no se va a hacer es maquillar el número. El hallazgo 18 pasa de
**«parcial, sin medida»** a **«medido, con suelo y con la deuda enumerada»**,
que no es lo mismo que cerrado y no se va a llamar así.

## 3.novodecies El dominio de tareas escrito dos veces, y la nota que lo justificaba

`app/services/task_service.py` tenía este comentario en la cabecera:

> `validate_task_transition` / `apply_status_side_effects` /
> `_TASK_VALID_TRANSITIONS` / `bulk_update_tasks` / `cascade_reschedule` **are
> NOT imported here on purpose**: this module defines its own procedural
> versions below (they carry extra logic such as OKR sync).

**Y era falsa.** Comparadas por AST —ancladas por nombre de función y no por
número de línea— las cuatro que este módulo duplicaba eran:

| función | diferencia con la del subpaquete |
|---|---|
| `validate_task_transition` | **idéntica** |
| `apply_status_side_effects` | **idéntica**. El «OKR sync» que la nota invocaba para justificar la copia está en las DOS, dentro de esta misma función |
| `cascade_reschedule` | idéntica menos una línea en blanco |
| `bulk_update_tasks` | idéntica menos **un bloque**: la llamada a `enforce_abac` |

O sea: la versión local no tenía lógica extra, tenía **una comprobación de
autorización de menos**. Y `endpoints/tasks.py` importa la de aquí.

### La corrección honesta, porque la primera lectura fue mía y era falsa

Lo primero que se escribió sobre esto —en el código y aquí— fue que
`POST /tasks/bulk-update` «se saltaba la evaluación ABAC». **No es cierto, y se
supo ejecutándolo**: con una política `deny` activa sobre `task`, esa ruta
devuelve 403 **antes de entrar al manejador**, porque la dependencia ABAC de los
routers ya la evalúa. El test que iba a demostrar la brecha demostró lo
contrario, que es para lo que sirven.

El motivo de que la tape es incómodo y es el hallazgo de verdad:
**`ABACService.evaluate_access` no usa el `resource_id`.** Lo recibe, lo mete en
el detalle de auditoría y no lo mira para decidir; `is_policy_applicable` ni
siquiera lo acepta. Con `action` pasa lo mismo. La decisión sale del rol, del
`resource_type` y de los atributos del usuario, así que la evaluación «por
tarea» y la del router dan **siempre el mismo veredicto**.

Consecuencias, las dos:

* lo que faltaba en la copia era **código de autorización latente, no una
  brecha**. Se arregla igual —una comprobación que debería estar y no está es un
  defecto aunque hoy la tape otra capa—, pero no se vende como brecha cerrada;
* **ABAC por recurso concreto no está implementado**, por mucho que la API pasee
  el `resource_id` por seis capas hasta el motor. Y había una nota en
  `app/core/abac_dependency.py` que decía que las llamadas explícitas «aportan
  grano más fino» **porque** pasan el id: esa frase era inexacta y se corrige
  allí mismo. Arreglarlo de verdad exige resolver atributos del recurso, que es
  diseño de producto; queda anotado, no disimulado, y con un test que lo fija
  (`test_el_motor_abac_ignora_el_resource_id`) para que el día que se implemente
  haya que cambiarlo a mano.

### La tabla de transiciones, que tampoco era la misma

`_TASK_VALID_TRANSITIONS` existía dos veces y **las dos copias diferían en una
entrada**: `todo → done` estaba permitida en `task_service.py` —la que se
ejecuta— y prohibida en `tasks/core.py`. Ningún test cubría esa transición, así
que nada lo habría dicho.

Se unifica en **la viva**, deliberadamente: marcar hecha una tarea pequeña sin
pasar por `in_progress` es el gesto normal de un tablero, y cambiar eso en
producción es una decisión de producto, no un arreglo de auditoría. Se comprobó
antes de decidir que nadie lee `Task.started_at` salvo el propio asignador de
sellos, así que saltarse `in_progress` no deja ningún cálculo de duración a
medias.

Y encima de las dos tablas había un comentario que decía «toda transición entre
estados está permitida» mientras la tabla de debajo prohibía la mitad. Corregido
en lugar de borrado: lo que sí es verdad —que la máquina es restrictiva, que la
trazabilidad va por `TaskMovementLog`, y por qué `todo → done` se queda— merece
quedar escrito.

### `TaskService`: 387 líneas y ningún sitio de llamada

Once métodos, un espejo exacto de las funciones procedurales, y **nadie la
importaba** salvo el `__init__` del subpaquete, que tampoco importa nadie.

Se comparó método a método contra la versión viva, normalizando `self.db`→`db` y
`self.current_user`→`current_user`. En las once parejas el resultado fue el
mismo: **la versión viva es un superconjunto estricto**. Lo que la copia muerta
NO tenía:

* `.get` y `.add_comment` → sin el acotado por `Project.organization_id`, así
  que buscaban la tarea por id **en todos los tenants**;
* `.cancel` → igual, y sin el 400 de «ya está cancelada»;
* `.bulk_update_dates` → sin la llamada a `enforce_abac` por tarea;
* `.create_dependency` → sin reactivar una dependencia borrada en lógico, así
  que daba 409 y dejaba al usuario sin salida;
* `.delete_dependency` → `db.delete(dep)` **físico**, cuando la convención de la
  tabla es `is_active`.

No era una alternativa: era la versión de antes de los arreglos de tenant (#62)
y de ABAC, esperando a que alguien la resucitara. Borrada.

### El guardián

`tests/test_dominio_de_tareas_una_sola_vez.py` comprueba con `is` —y no con
`==`— que lo de `task_service` y lo del subpaquete son **el mismo objeto**: dos
funciones con el mismo cuerpo son iguales para cualquier comparación razonable y
siguen siendo dos sitios donde arreglar el mismo defecto.

## 3.septdecies El panel de sesiones activas estaba vacío para todo el mundo

`user_sessions.organization_id` existe desde la auditoría #7 —lo dice el
comentario que lleva al lado en el modelo— y **nadie la rellenaba**.
`register_or_rotate_user_session` construía la fila con `user_id`,
`refresh_token_jti`, `auth_method` y `created_at`, y nada más.

El filtro de tenant es `organization_id == org`, y una fila con NULL **no la ve
su propia organización**. Medido de punta a punta:

```
GET    /auth/sessions/active   → 0 sesiones, siempre, a cualquier usuario
DELETE /auth/sessions/{id}     → ninguna fila que revocar
```

Y sin un solo error en los registros: una lista vacía, que es exactamente lo que
no se investiga. Es el defecto de §3.quater otra vez, con un agravante: «revocar
este dispositivo» no es una comodidad, es **la palanca que tiene un usuario que
ve un inicio de sesión que no reconoce**. Llevaba muerta desde que se añadió la
columna.

### Por qué el sellado automático no lo salvaba

Y no es un descuido del sellado: **iniciar sesión es anónimo por definición**.
Cuando se crea esa fila todavía no hay usuario autenticado, así que la sesión de
base de datos no tiene contexto publicado y `_sellar_organizacion` sale por la
puerta de atrás. Es el mismo hueco que en `get_current_user` y en los tres
WebSocket, y la respuesta es la misma que documenta `publicar_contexto_de_tenant`:
la organización se pregunta explícitamente, **después** de resolver por id el
sujeto que todavía no se sabe de quién es.

`_organizacion_del_usuario(db, user_id)` hace esa consulta con la sesión sin
contexto —sin filtrar, que es lo correcto aquí— y devuelve `None` sólo si el
usuario no existe: `users.organization_id` es NOT NULL, así que no hay usuario
sin organización, ni siquiera un superadmin.

### Las filas que ya estaban

Se curan solas al rotar el refresh —un usuario que vuelve a entrar recupera su
panel— y además la revisión **095** rellena de una vez las que no vuelvan
pronto, que son las que importan: una sesión abierta hace semanas seguiría
invisible.

El relleno sale de `users.organization_id` por `user_sessions.user_id`, y **no
recurre a la organización por defecto**. Las revisiones 076 y 080 lo hacían, y
eso reparte a un tenant las filas de los demás. Una sesión cuyo usuario no
existe se queda como está: no se puede usar para autenticarse —el refresco busca
por usuario— y lo que hay que hacer con ella es caducarla, no adoptarla.

Verificada ejecutándola sobre SQLite con cuatro casos —dos que se rellenan, una
huérfana que se queda, una que ya tenía organización y no se toca—, con segunda
pasada idempotente y `downgrade` que no revierte y lo dice.

### Cómo salió

Registrando los escuchadores de tenant en la suite (§3.sexdecies). No lo
encontró ningún detector: los cuatro de esta auditoría buscan nombres que no
existen, y aquí **todos los nombres existen**. Lo que faltaba era un valor. Ese
es el límite de esa familia de detectores y conviene tenerlo escrito: una
columna que nadie rellena es invisible al análisis estático, y sólo se ve
corriendo el filtro que la usa.

## 3.sexdecies El filtro de tenant, registrado en la suite — y lo que salió debajo

La decisión que llevaba abierta toda la auditoría: `tests/conftest.py` usaba un
`sessionmaker` plano y los tres mecanismos de aislamiento se registran sobre
`SessionLocal`, así que **ninguno se disparaba en ningún test**. Eso es lo que
dejó vivir el apagón de §3.bis y el `TypeError` de su rama vecina.

`TestSession` usa ahora `class_=TenantSession` y tiene registrados el
escuchador `do_orm_execute` y el sellado `before_flush`, los mismos de
producción.

**Corrección de lo que se escribió aquí antes de ejecutarlo.** La primera
versión de esta sección decía que el cambio era «seguro por construcción» y que
«la suite entera pasa, sin declarar ni una excepción». Lo primero es medio
verdad y lo segundo era **falso**, y se supo al lanzar la suite: **23 tests en
rojo**. Ninguno hizo falta declararlo como excepción, pero tampoco pasaron solos.
Catorce eran del propio banco de pruebas —filas sembradas sin organización que
ahora nacen con la de la sesión—, **siete destaparon defectos de producción** y
dos eran regresiones de esta misma jornada. El desglose completo está en
**§3.vicies**; aquí quedan los cuatro que explican el cambio del banco de
pruebas.

Lo de «seguro por construcción» sí es cierto en su mitad: las tres capas salen
por la puerta de atrás cuando `info` no trae `is_superadmin` («sesión no
inicializada»), así que un test que no autentica no cambia. Lo que no se vio es
que el **sellado** tiene otra puerta —sale si no hay `organization_id`— y que
la sesión del fixture `db` no publicaba ninguno.

### 1. El fixture `db` sellaba con NULL (artefacto, y del gordo)

Toda fila creada por un test con `db.add(...)` nacía con `organization_id` NULL,
y la petición HTTP siguiente —que sí tiene contexto— no la encontraba. Síntoma:
`test_imputation_rejects_closed_task_status` esperaba el 400 de «tarea cerrada»
y recibía **404**, porque su tarea era invisible.

La sesión del fixture publica ahora contexto, y el reparto es deliberado:
`organization_id` de los usuarios de test **y** `is_superadmin=True`. Escribir
sella —las filas caen donde la API las ve—; leer no filtra —para poder
comprobar lo que la API debería haber escondido—. Quien quiera comprobar el
aislamiento de verdad no usa esa sesión: va por HTTP con dos tokens.

### 2. `test_sellado_de_organizacion.py` documentaba la decisión como pendiente

Su cabecera decía que registrar los escuchadores en la factoría era «lo correcto
a medio plazo» y quedaba anotado en el traspaso. Ya está hecho, así que la nota
se corrige, el fixture deja de enganchar a mano lo que ya está enganchado, y el
test del job de fondo se monta su propia sesión sin contexto — que es justo lo
que quiere probar.

### 3. La configuración de SSO huérfana ya no nacía huérfana (artefacto)

`test_resolve_sso_org_rejects_orphan_autoprovisioning` creaba un `SSOConfig` con
`organization_id=None` y esperaba que resolverlo fallara. Con el sellado puesto,
la fila ya no nace sin organización por mucho que se pida. El caso que defiende
—una configuración anterior al sellado— se construye ahora con un `UPDATE`
directo, y el test vuelve a probar lo que decía probar.

### 4. Y los que no eran artefactos

El panel de sesiones activas, vacío para todo el mundo (§3.septdecies), y los
tres defectos de aislamiento de §3.vicies: mover un usuario de organización
devolvía 500 con el cambio ya hecho, y el traspaso de una suscripción push no
veía ni actualizaba la fila ajena, que es justo lo que decía arreglar.

Y una `fila_global(db)` en `tests/conftest.py` para los pocos casos que crean
filas **sin** organización a propósito —los que prueban qué pasa con un valor
global—, porque pasarle `None` ya no basta: el sellado rellena precisamente los
`None`.

**Lo que esto dice del método**, que es la parte reutilizable: registrar el
filtro en la suite no fue «un cambio de configuración de los tests». Fue
encender una luz. La mayoría de los tropiezos se arreglaron en el propio banco
de pruebas; los que no, eran código que llevaba tiempo sin funcionar en
producción y que **ningún test podía haber visto antes**, porque ningún test
corría con el filtro. Incluidos los tests que creían estar probando justo eso:
uno de ellos activaba el filtro a mano sobre una sesión que no era la de
producción, y por eso daba por bueno un arreglo que allí no funcionaba.

## 3.quaterdecies El tercer detector: siete funciones más, y dos que fallaban en silencio

El frente que quedaba señalado, cerrado. `audit_enum_members.py` mira
`Enumerado.valor`; `audit_model_attrs.py` mira `Modelo.columna`; ninguno de los
dos puede ver `fila.columna`. `scripts/audit_instance_attrs.py` sí.

### Cómo se infiere el tipo sin inferir tipos

Cuatro formas cubren el código real de este repositorio: el bucle sobre una
consulta, la comprehensión sobre una consulta, la asignación desde una consulta
que devuelve una fila (`.first()`, `.one()`…) y el parámetro anotado. **Y un
nombre religado más de una vez se descarta**, por cualquier vía.

Lo que **no** cubre, y queda dicho: variables que vienen de una llamada a un
servicio, donde haría falta seguir el tipo de retorno.

### Lo que encontró: diez accesos, siete funciones roídas

| dónde | qué | qué pasaba |
|---|---|---|
| `agent_execution_service` | `execution.updated_at` | **reventaba siempre**: el estado de una ejecución de agente de IA no se podía consultar |
| `ai_planning_service` | `ticket.assignee_id = …` | **asignación silenciosa**: aceptar un triaje de IA cambiaba prioridad y tipo y **no asignaba el ticket a nadie** |
| `bookings_service` ×3 | `opp.amount` | convertir una oportunidad ganada en proyecto reventaba |
| `epics_service` | `t.assigned_to_user_id` | el detalle de un epic **no se podía leer** en cuanto tenía una tarea |
| `security_observability` | `det.mttd_seconds = …` | **asignación silenciosa**: el tiempo hasta la detección se calculaba y se tiraba |
| `change_management_service` | `change.assigned_to_id` | **ningún aviso a los interesados de un cambio llegaba nunca** — ni al solicitante, ni al aprobador, ni al responsable |
| `smart_catalog_service` | `svc.popularity_score` | tras un `hasattr` correcto: la actualización de popularidad **no actualizaba nada** y devolvía `updated: 0` sin error |

Los nombres correctos eran `completed_at`, `assigned_to_user_id`,
`expected_revenue`, `assignee_id` y `owner_id`. Los otros dos no existen y **no
se inventan**: ver abajo.

### Lo que este detector enseña y los otros dos no

**La asignación es peor que la lectura.** `fila.columna_que_no_existe` al leer
lanza `AttributeError` y alguien ve un 500. Al **escribir**, SQLAlchemy no se
queja: se queda un atributo de Python que no persiste. Dos de los diez eran así,
y los dos tiraban un cálculo a la basura sin un solo error en los registros. Un
fallo silencioso es peor que un 500 — el 500 se investiga.

**Y un segundo defecto detrás del primero.** En `bookings_service`, el
`OpportunityStage.closed_won` inexistente abortaba la función **antes** de llegar
al `opp.amount`. El segundo sólo se vio al arreglar el primero, y sólo porque se
volvió a pasar el detector después. Es la misma lección que ya dio la pasarela
de correo, donde había tres apilados: **arreglar el primer defecto de una
función no la arregla; hay que volver a medir**.

### Dos que no se inventan

**`det.mttd_seconds`.** El tiempo hasta la detección es derivable de
`detected_at - first_seen_at`, y las dos columnas ya se guardan, así que añadir
una tercera sería duplicar información. Lo que hacía falta era **dejar de
fingir que se guarda**: el bloque entero se quita, con la normalización de zona
horaria que sólo servía para eso.

**`svc.popularity_score`.** La popularidad se calcula en la misma función a
partir del recuento de tickets, así que guardarla sería un caché que hay que
invalidar. Se **devuelve** en la respuesta, con `persisted: False`, y la clave
`updated` se conserva —era API publicada— pero ahora dice la verdad: cero, y por
qué.

### El guardián, y su honestidad sobre sí mismo

`tests/test_atributos_de_instancia_existen.py`, tolerancia cero, con
`CONOCIDOS` **vacía**. Importa el propio script de medición en vez de
reimplementar la regla, y tiene un test que comprueba que la inferencia sigue
funcionando —si dejara de reconocer las formas del repositorio, no encontraría
variables que vigilar y el guardián pasaría por vacío—.

Comprobado contra el código anterior con `git worktree`: **encuentra los diez**.

> **Y el detector se equivocó dos veces antes de servir, otra vez.** La primera
> versión daba **veinte** accesos, y **diez eran un único falso positivo**: en
> `_get_capacity_plans`, la variable `p` es primero el `Project` de una
> comprehensión y después el `CapacityPlan` de un `for p in plans`. Descartar
> los nombres ligados a dos *modelos* distintos tampoco bastaba —la segunda
> ligadura no es una consulta, así que el detector no le asignaba tipo y no veía
> el conflicto—: hay que contar **todas** las ligaduras, no sólo las que se
> saben tipar. Tercer detector, tercera vez que hay que ajustarlo midiendo.

## 3.terdecies El hallazgo 22, cerrado: 257 → 0

`scripts/audit_db_access_in_api.py` da **cero puntos de acceso a datos en toda
`app/api/`**. Con la misma regla, sobre el histórico:

```
antes de la tanda 1 (collaboration)   257 puntos de acceso en 41 ficheros
al empezar la última jornada           46 en 23
a media jornada                        13 en 12
ahora                                   0 en 0
```

Quedan **109 fronteras de transacción** —`commit`, `rollback`, `close` y
`refresh`— y quedan **a propósito**: el servicio prepara y el endpoint confirma.
`refresh` es releer la fila que el servicio acaba de devolver para recoger lo
que pone la base, y va pegado a un `commit`; moverlo obligaría a que el servicio
confirme, que es lo contrario de lo que estas tandas hicieron.

### Y el guardián, que es la mitad del cierre

`tests/test_capa_api_sin_acceso_a_base.py`, tolerancia cero. **Importa el propio
script de medición** en vez de reimplementar la regla: dos implementaciones de
la misma pregunta es exactamente cómo aparecieron las dos puertas del
marketplace. Y tiene dos tests más que evitan que pase por vacío: uno comprueba
que el detector sigue viendo ficheros, y otro que las fronteras de transacción
**siguen** en el endpoint —si caen a cero, alguien movió las transacciones a los
servicios, y eso es un cambio de arquitectura que merece su propia
conversación—.

### De los trece últimos, uno traía defecto

`PATCH /automation-workflows/{wf_id}/steps/{step_id}/retries` buscaba el paso
así:

```python
db.query(WorkflowStep).filter(
    WorkflowStep.id == step_id,
    WorkflowStep.workflow_id == wf_id,
).first()
```

Los dos identificadores vienen de la ruta y **no había ninguna comprobación de
a quién pertenece el workflow**. En producción el filtro implícito de
`TenantSession` lo evitaba —`WorkflowStep` tiene `organization_id`— pero era la
única capa, y esto **escribe**: cambia la política de reintentos del paso de
otro cliente. Es el mismo perfil que el `/batch-score` del CAB, y la misma
conclusión: la guarda hace falta aunque hoy haya una capa que lo tape.

Los otros doce eran movimientos sin defecto, y eso también hay que decirlo tal
cual: el filtro ya estaba y era el correcto en los doce.

### Tres detalles que se fijan con test porque se pierden al mover código

**El `["__none__"]` del asignador semántico no es decorativo.** Una organización
sin usuarios activos tiene que dar **cero candidatos**; una lista vacía
significaría «sin restricción», que es justo lo contrario. Al mover la función
es exactamente la clase de detalle que se simplifica sin querer.

**El condicional de `bi_etl` *parece* el defectuoso y no lo es.** Cuatro veces
en esta auditoría apareció `if org_id: q = q.filter(...)`, que sin organización
devuelve las filas de todos. El de `bi_etl` tiene rama `else` que filtra por
`IS NULL` —el valor global del despliegue—, así que **los dos caminos acotan**.
Queda con test para que nadie lo «arregle» rompiéndolo.

**Y el `fail-open` de la política de MFA.** Si el `organization_id` de un usuario
no resuelve a ninguna fila, no se exige segundo factor. Es lo correcto —bloquear
el acceso por una fila que falta convertiría un dato inconsistente en una caída
de login— pero es una decisión, no una consecuencia, así que está escrita y
tiene test.

### Y una función que ahora tiene nombre: `organizacion_existe`

La comprobación anti-enumeración de `predictive_observability` vive en
`app/core/tenancy.py`, junto a `assert_org_id_is_own`, porque es la misma
familia: **lo que se puede y no se puede saber sobre una organización ajena**.
Y no filtra por organización a propósito: quien la usa comprueba *antes* que el
id recibido es el propio, y separar las dos preguntas es lo que permite devolver
404 en los dos casos —«no existe» y «no es tuya» tienen que ser
indistinguibles—.

## 3.duodecies El mismo detector sobre las columnas: diez funciones más que no funcionaban

El frente que §3.undecies dejó **medido y abierto**, cerrado. `Ticket.category`,
`SLAPolicy.response_hours` y `Ticket.requester_phone` eran columnas de modelo, no
valores de enumerado, así que el detector de enumerados no las veía. El hermano
está en `scripts/audit_model_attrs.py` y resuelve el lado de la clase con
`hasattr` sobre la clase **mapeada de verdad**, no por AST: así cubre columnas,
relaciones, propiedades híbridas, métodos y todo lo heredado.

**43 candidatos en 27 pares (clase, atributo)** sobre 391 clases mapeadas.
Verificados uno a uno, **ninguno era un falso positivo**: los 43 son nombres
equivocados o columnas que faltan.

### Lo que rompía cada uno

Diez funciones completas. Y tres de ellas estaban escondidas detrás de un
`hasattr` **correcto** sobre una columna ausente, que es el peor caso: parece
una defensa y es un interruptor de apagado.

| qué | consecuencia |
|---|---|
| `cmdb_service` con `CMDBItem.project_id` | el `else` del `hasattr` **se saltaba el filtro de organización entero** en el listado de CMDB, dejando un aviso en el log que parecía informar de una limitación temporal del despliegue |
| `salesforce_service.find_opportunity_by_external_id` | devolvía **siempre None**, así que la sincronización **duplicaba todas las oportunidades en cada pasada** |
| la comprobación «P1 sin incidencia mayor» | reportaba **todos** los P1, siempre: un hallazgo de cumplimiento que salta siempre no informa de nada |
| aplicar una plantilla de proyecto | `Deliverable(billing_pct=...)` → `TypeError`: fallaba en cuanto la plantilla traía un entregable |
| importar imputaciones desde CSV | `Imputation(work_type=...)` → `TypeError`, fila por fila |
| la detección automática de problemas | `Ticket.category` no existe: **no funcionó nunca** |
| el cálculo automático de reconocimiento de ingresos | `RevenueRecognitionRule.is_active` no existía |
| la estimación de horas por tareas similares | `Task.actual_hours` no existe, así que **caía siempre** en la heurística por palabras del título |
| las tareas de un sprint | `Task.sprint_id` no existe: el enlace es la tabla `sprint_tasks` |
| la correlación de alertas por CI raíz | las tres columnas de `CMDBRelation` con otro nombre; el `except` lo tragaba y devolvía **siempre cero** |
| el comentario de la IA en el ticket | `TicketComment(is_internal=...)` → `TypeError` tragado por un `except`: **la resolución nunca llegaba al ticket** |
| el enlace de tickets duplicados | igual: el ticket se marcaba duplicado **sin quedar enlazado** a su original |
| la carga por agente (tres informes distintos) | `Ticket.assignee_id` ×11, cuando la columna es `assigned_to_user_id` — `assignee_id` es la de `Task`, y de ahí viene la confusión |

### Los tres grupos, y qué se hizo con cada uno

**Nombres equivocados —34 sitios—: renombrados.** Mecánico y verificable.
Además de los de arriba: `ClientHealthSnapshot.created_at` (es `snapshot_at`),
`Contract.amount` (`total_amount`), `Deliverable.due_date` (`planned_date`),
`Expense.date` (`expense_date`), `KBArticle.is_published` (`is_public`),
`Task.created_by_user_id` (`created_by`), `Alert.message` (tiene `title` y
`description`).

> **Y uno que el detector no podía ver.** Al arreglar `KBArticle.is_published`
> apareció, dos líneas más abajo, `art.content` — y el cuerpo del artículo es
> `art.body`. `art` es una **instancia**, y el acceso a un atributo de instancia
> no se puede comprobar estáticamente. Consecuencia: el texto del artículo
> entraba vacío en la puntuación, así que la sugerencia de artículos del
> copiloto se decidía **sólo por el título**. Queda dicho como límite del
> detector: cubre el lado de la clase, no el de la instancia.

**Conceptos que el esquema modela de otra forma —4 sitios—: reimplementados.**
Las tareas de un sprint pasan por la tabla de unión; las horas reales de una
tarea se calculan con una subconsulta de imputaciones; la clasificación de un
ticket es su elemento del catálogo de servicios —y eso queda escrito como
**lectura de la intención, no renombrado**, para que se revise—; y
`Imputation.work_type` **no se inventa**: si la columna del CSV llega, hoy se
descarta, que es preferible a no poder importar nada.

**Columnas que hacían falta de verdad —3—: añadidas**, con la revisión
`094_columnas_que_el_codigo_leia_sin_existir`. `deliverables.billing_pct`,
`opportunities.external_id` (indexada) y
`revenue_recognition_rules.is_active` (NOT NULL, rellenada a `true`). La
migración se verificó **ejecutándola de verdad**: upgrade, relleno, el
`NOT NULL` de verdad, el índice, que la segunda pasada no revienta, y el
downgrade completo.

**Y uno que no se toca.** `MajorIncident.tickets`: entre esas dos entidades no
hay ni columna ni tabla de unión, comprobado sobre `Base.metadata`. Inventar el
enlace es una decisión de diseño —¿un ticket pertenece a una sola incidencia
mayor, o varias comparten tickets?— y no se cuela en una tanda de otra cosa. Lo
que sí se hace es **decir la verdad**: la comprobación se declara no evaluable
mientras el enlace no exista, en vez de dar un falso positivo por cada P1.

### El guardián

`tests/test_atributos_de_modelo_existen.py`, de tolerancia cero, con una lista
`CONOCIDOS` de una sola entrada y su razón escrita. Y un segundo test que
**comprueba que esa excepción sigue siendo necesaria**: si alguien añade la
relación que falta, la entrada sobra y el test lo dice, así la excepción no se
queda ahí para siempre por inercia.

**Comprobado que discrimina, y con la cifra exacta:** ejecutado contra la
versión anterior del repositorio en un `git worktree`, encuentra **42** sitios
—los 43 candidatos menos el declarado en `CONOCIDOS`—. Escribí primero 43 y hubo
que corregirlo: la diferencia es de uno, y aun así se mide.

### Lo que este par de detectores dice sobre el conjunto

Entre los dos —enumerados y columnas— son **52 sitios** y **diecinueve
funciones completas** que no podían hacer su trabajo, encontrados por dos
scripts de treinta líneas cada uno. Ninguno lo veía `ruff`, ni el tipado, ni la
suite. La pregunta que los generó no era sobre seguridad ni sobre rendimiento;
era la más simple posible: **«¿existe lo que este código está nombrando?»**

Y la tercera versión de la misma pregunta —los atributos de **instancia**, que
el caso de `art.content` dejó señalada— está **hecha** en §3.quaterdecies: diez
accesos más, siete funciones roídas, y dos de ellas fallando en silencio. No
hizo falta inferir tipos de verdad: cuatro formas sintácticas cubren el código
real de este repositorio.

## 3.undecies La pregunta general, y las nueve vías que no podían funcionar

El hallazgo de §3.decies dejó una pregunta: **«¿cuántos más hay?»** La respuesta
son nueve, y son la mejor cosecha por unidad de esfuerzo de toda la auditoría:
un detector de treinta líneas.

### El detector

`scripts/audit_enum_members.py`. Recorre `app/` por AST y, para cada
`Enumerado.miembro`, comprueba que el miembro exista. Dos reglas:

* **la de la unión** — el miembro tiene que existir en **alguna** definición de
  ese nombre. Sin falsos positivos, así que puede ser de tolerancia cero;
* **la del import** — tiene que existir en la definición que **ese fichero
  importa de verdad**, siguiendo reexportaciones, incluidas las de
  `from ... import *`.

Las dos están como test en `tests/test_miembros_de_enum_existen.py`.

### Lo que encontró, y lo que pasaba en cada sitio

| dónde | qué usaba | qué pasaba |
|---|---|---|
| `inbound_email_service` | `TicketStatus.open` | **la pasarela de correo a ticket, entera**: cada correo entrante reventaba |
| `multichannel_service` | `TicketStatus.open` | lo mismo con **cada SMS entrante** |
| `asset_service` | `TicketStatus.open` | el ticket que agenda la renovación de un equipo |
| `bookings_service` ×2 | `OpportunityStage.closed_won` | **convertir una oportunidad ganada en proyecto**, roto en su primera línea útil |
| `metrics/okr_nps` | `OKRStatus.at_risk` | atrapado por un `except`: la métrica de progreso de OKR devolvía **lista vacía** en silencio |
| `change_impact.py` ×2 y `worker.py` | `ChangeStatus.in_approval` | los tres de §3.decies |

Los valores correctos eran `new` —que además es el `default` de la columna y lo
que usan las **otras tres** vías de creación de tickets—, `won`, y, para el de
OKR, sólo `active`: «en riesgo» no es un estado que exista ni una columna que se
pueda consultar, y el docstring de la función ya decía «por objetivo OKR
activo».

### Y detrás del primero había tres más

Al escribir el test de la pasarela de correo —**que no tenía ninguno**—
aparecieron, encadenados uno detrás de otro:

1. **`SLAPolicy.response_hours` no existe.** Las columnas son
   `p1_response_hours` … `p4_response_hours`, una por prioridad. Reventaban el
   `order_by` de la consulta y los dos cálculos de vencimiento. Está en la vía
   de correo **y** en la de SMS.
2. **El vencimiento se calculaba a mano**, `now + timedelta(...)`, ignorando el
   horario laboral y los festivos que `SLAPolicy` declara — y en la de SMS con
   un `datetime(...).__class__.fromtimestamp(...)`, que es la misma suma de
   segundos escrita de forma más rara. Las dos cosas ya estaban resueltas en el
   repositorio y sin usar aquí: `resolve_sla_policy_for_ticket` elige la
   política por contrato, cliente y defecto, y `calculate_sla_due` calcula los
   dos vencimientos con aritmética de horas laborables. Ahora se usan.
3. **`Ticket.requester_phone` no existe**, y estaba escrito así:

   ```python
   requester_phone=from_phone if hasattr(Ticket, "requester_phone") else None,
   ```

   Es la forma **más dañina** del `hasattr` defensivo: protege el *valor* y no
   la *palabra clave*, así que SQLAlchemy recibe igual `requester_phone=None` y
   responde `TypeError: 'requester_phone' is an invalid keyword argument for
   Ticket`. Parece que hace el campo opcional y lo que hace es reventar siempre.
   El teléfono queda en `requester_name` y en la descripción, que es donde
   estaba de verdad; añadir la columna es decisión de producto.

Y en el ticket de renovación de activo, un cuarto: se construía **sin
`number`**, y la columna es NOT NULL, así que detrás del `AttributeError` venía
un `IntegrityError`.

### Por qué sobrevivieron, que es la parte que importa

**Ninguna de las tres vías tenía un solo test.** Los defectos no son sutiles
—son un `AttributeError` en la primera línea útil— pero viven en caminos que
nadie ejercitaba: no los ve `ruff`, que no resuelve el enumerado; no los ve el
tipado; y no los ve una suite que no llama a la función. Los tests nuevos son la
cobertura que faltaba, no sólo la comprobación del arreglo.

### El detector estuvo mal dos veces antes de servir, otra vez

La misma lección que con el detector de rutas del frontend, y conviene que quede
por escrito porque volvió a pasar:

1. Escribí que el fichero de tests cazaba los nueve. **Falso**: la regla de la
   unión coge seis, porque el enumerado muerto **sí** tenía `in_approval` y para
   esa regla aquellos tres sitios eran correctos.
2. Escribí entonces que la regla del import cazaba los tres de `ChangeStatus`.
   **También falso**: su primera versión no seguía las reexportaciones, así que
   se callaba justo en los casos que motivaron el test — y sólo cogía tres, los
   de oportunidades y el de OKR.
3. Y la segunda versión seguía las reexportaciones **con nombre**, pero los
   enumerados del Service Desk llegan por `from ... import *`. Con las estrellas
   resueltas coge los nueve, comprobado ejecutándola contra el código anterior
   en un `git worktree`.

**Una afirmación sobre qué caza un detector no vale hasta ejecutarla contra el
código defectuoso.** Tres intentos, tres mediciones, y sólo la tercera era
cierta.

### El frente que esto abre, medido y NO cerrado

La misma pregunta aplicada a las **columnas de modelo** —que es lo que eran
`SLAPolicy.response_hours` y `Ticket.requester_phone`— tiene su propio detector
en `scripts/audit_model_attrs.py`, que resuelve el lado de la clase con
`hasattr` sobre la clase mapeada de verdad. Da **35 accesos a atributos que no
existen y 8 constructores con una palabra clave que no es atributo**, sobre 391
clases mapeadas.

**Cerrado en §3.duodecies**, que es la sección de arriba: los 43 verificados uno
a uno, **ninguno era un falso positivo**, y entre ellos diez funciones completas
que no podían hacer su trabajo. Cuando escribí esto eran candidatos y así había
que decirlo; ahora están medidos.

## 3.decies El estado `in_approval` no existe, y por eso el scoring del CAB no corría

Salió de mover a servicio los dos puntos de acceso de
`endpoints/service_desk/change_impact.py`. Lo que había detrás es más grande que
el movimiento, y es la clase de defecto más difícil de ver: **dos enumerados con
el mismo nombre y valores distintos**.

### Los dos `ChangeStatus`

| dónde | valores |
|---|---|
| `app/models/service_desk/_enums.py` | draft, submitted, **cab_review**, approved, scheduled, in_progress, implemented, post_review, closed_success, closed_failed, cancelled |
| `app/services/service_desk/change_management_service.py` | draft, submitted, **in_approval**, approved, scheduled, in_progress, completed, rolled_back, cancelled |

El primero es el que usa la **columna** `sd_change_requests.status`. El segundo
era un enumerado local del servicio, y **no lo usaba nadie**: las funciones de
su propio módulo importan el del modelo, y ni `app/` ni `tests/` lo importan —
comprobado. Era el único sitio del repositorio donde `in_approval` existía.

### Tres consumidores lo daban por bueno

Los tres importan el enumerado del **modelo** y escriben
`ChangeStatus.in_approval`. Medido, cada uno con su consecuencia:

1. **`POST /sd/changes/batch-score`.** La referencia era **incondicional**, así
   que el endpoint respondía **500 siempre**:
   `AttributeError: type object 'ChangeStatus' has no attribute 'in_approval'`.
   **Nunca puntuó un solo cambio.**
2. **`GET /sd/changes/cab-dashboard`.** El valor por defecto del parámetro era
   `"submitted,in_approval"`, y `in_approval` se caía del filtro por no estar en
   el enumerado. El panel del CAB listaba **sólo `submitted`** y **no mostraba
   ninguno** de los cambios que están de verdad esperando decisión del CAB, que
   es `cab_review`. Y si el cliente mandaba un estado inexistente se llegaba a
   la rama de respaldo y también devolvía 500.
3. **La tarea de Celery `change_impact_batch_score`**, programada **cada 10
   minutos**. Mismo `AttributeError`, atrapado por su `except` exterior, que
   dejaba una línea de log y devolvía. **La pasada programada llevaba fallando
   en cada tic**, así que `auto_risk_score` sólo se rellenaba en la transición a
   `submitted` (`change_service.py`) y **la auto-aprobación de cambios estándar
   de bajo riesgo no se ejecutaba nunca**.

Y un cuarto sitio, con el mismo error en forma de cadena:
`change_service.py` re-puntuaba en `new_status in ("submitted", "in_approval")`,
así que esa mitad de la condición nunca se cumplía.

### Corrección de mi primer diagnóstico

Al ver la consulta de `/batch-score` escribí que **auto-aprobaba las solicitudes
de cambio de todos los clientes**: no filtra por organización y el bucle
escribe, firmando la aprobación con el id de quien lanza la pasada.

**El filtro faltaba de verdad, pero esa escritura cruzada nunca fue
alcanzable**: el endpoint reventaba con el `AttributeError` antes de llegar a la
consulta. Era un defecto **latente**, no un incidente. La guarda hace falta
igual —ahora que el endpoint funciona, sin ella sí lo sería— pero decirlo de la
otra manera sería exagerar lo que pasaba. Es la misma corrección que hubo que
hacer con el «apagón» de §3.bis, y por la misma razón: describir el defecto por
la forma del código en vez de por lo que hace al ejecutarse.

### Lo que se hace

* `ESTADOS_PENDIENTES_DE_CAB` se construye **desde el enumerado del modelo**
  (`submitted`, `cab_review`), así que un renombrado revienta ahí y no en un
  `AttributeError` a mitad de una petición.
* Los cuatro sitios usan esa constante: el panel, su rama de respaldo, la tarea
  de Celery y el re-scoring en la transición.
* **El enumerado local muerto, fuera.** Dos enumerados con el mismo nombre y
  valores distintos, uno de ellos sin usar, es una trampa: se importa el que no
  toca y el intérprete no se queja hasta que se accede al miembro que falta.
* Y el filtro explícito por organización en las dos consultas, más un tope
  configurable (`CHANGE_BATCH_SCORE_MAX`, en `.env.example`) para la pasada del
  endpoint — la tarea de Celery sí tenía `limit(50)`; el endpoint, ninguno.

### El guardián, y que sirve

Un test recorre `app/` **por AST** buscando `ChangeStatus.<algo>` y comprueba
que `<algo>` es un miembro real del enumerado del modelo. Comprobado contra el
código de antes con un `git worktree`: **encuentra exactamente los tres
sitios**.

```
app/worker.py:1263 -> ChangeStatus.in_approval
app/api/v1/endpoints/service_desk/change_impact.py:207 -> ChangeStatus.in_approval
app/api/v1/endpoints/service_desk/change_impact.py:258 -> ChangeStatus.in_approval
```

Eso es lo que hace que sea un guardián y no un test de acompañamiento: se
verificó que **falla contra el código defectuoso** antes de darlo por bueno.

> **Y la pregunta que este hallazgo deja abierta**, porque el patrón puede
> repetirse: ¿cuántos más hay? El guardián sólo mira `ChangeStatus`. La
> pregunta general —«¿hay dos clases con el mismo nombre y contenido distinto en
> el repositorio, y alguien importa la que no toca?»— tiene respuesta por AST y
> **no se ha hecho**. Queda anotada como candidata para la próxima pasada,
> porque el modo de fallo es exactamente el de aquí: un `AttributeError` en un
> camino que nadie ejercita.

## 3.novies Las credenciales de e-firma de un cliente eran el valor global del despliegue

Salió de mover a servicio los tres puntos de acceso de `endpoints/esign.py`.
`dynamic_forms`, `client_portal` y `esign` quedan en **0**.

### Lo que había

Dos ayudantes locales que buscaban `AppSetting` por clave, y nada más:

```python
def _get_esign_setting(db: Session, key: str) -> Optional[str]:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row and row.value else None
```

**Sin organización.** Y lo que guardan son las credenciales de DocuSign y de
Adobe Sign de cada cliente: su `integration_key`, su `secret_key`, su
`account_id` y —lo más grave— los **tokens de acceso y de refresco** que
devuelve el OAuth. Tres consecuencias, en orden:

1. **La escritura creaba la fila con `organization_id` a NULL**, que en
   `AppSetting` significa «valor global del despliegue». El primer cliente que
   configurara su DocuSign lo dejaba como valor de **todos**.
2. **La lectura devolvía la primera fila con esa clave**, sin mirar de quién es.
   Un cliente firmaba con la cuenta de DocuSign de otro.
3. **Al completar el OAuth**, el token de acceso de un cliente quedaba guardado
   como global: cualquier otro enviaba sobres con su token.

No es un descuido aislado: son **26 sitios de llamada** en el fichero, incluidos
los cuatro pasos de los dos flujos de OAuth y los dos endpoints que guardan un
token recibido a mano.

### La señal que explica por qué la comprobación nunca se escribió

Las **nueve** funciones que usaban esos ayudantes recibían el sujeto y lo
descartaban:

```python
def get_esign_config(
    db: Session = Depends(get_db),
    _:  User    = Depends(require_admin),
):
```

**Nueve de nueve.** No había a quién preguntarle la organización porque el
parámetro no tenía nombre. Es el mismo descarte que dejó sin comprobar el coste
activo de un usuario (§3 de `baselines_y_costes`), y aquí aparece nueve veces
seguidas en el mismo fichero.

Hay un test que lo comprueba **por AST**: si alguien escribe una décima función
que lea o escriba ajustes de e-firma sin recibir el sujeto con nombre, se pone
en rojo. No comprueba el arreglo; comprueba que la forma que causó el defecto no
vuelve.

### La regla que se aplica

La que ya usa el resto del repositorio para `AppSetting` —ver
`governance_compliance_service`—: **lo propio si existe, y si no el global**, que
es el valor que trae el despliegue. La escritura, siempre en lo propio.

Eso importa para no romper nada: las filas que ya existen en un despliegue en
marcha son globales, así que **siguen sirviendo de respaldo** y el
comportamiento de hoy se conserva hasta que cada cliente guarde lo suyo.

### Y una transacción de siete en una

`PATCH /esign/config` guarda siete claves, y el ayudante hacía `commit()` en cada
una: **siete transacciones para una petición**. Un fallo a mitad dejaba unas
credenciales guardadas y otras no —con la mitad de un DocuSign nuevo y la mitad
del viejo, que es peor que no haber guardado nada—. Ahora el servicio no
confirma y el endpoint hace un solo `commit` al final.

### Y `/predictive/stats`: 12 consultas por ticket abierto, medidas

Estaba en la lista de «defectos localizados y no arreglados» desde la tanda 1.
Cargaba **todos** los tickets abiertos como objetos del ORM y, para cada uno,
llamaba a `predict_ticket` y a `predict_sla_breach`. Medido con la sesión real:

```
 1 ticket abierto  ->    12 consultas
 5 tickets         ->    60 consultas
20 tickets         ->   240 consultas
```

Exactamente **12 consultas por ticket**, y lineal. Con 500 tickets abiertos son
**6.000 consultas en una sola petición**, más 500 objetos del ORM en memoria.

El tope —`PREDICTIVE_STATS_MAX_TICKETS`, declarado en `.env.example`— **no
arregla el N+1: lo acota**, que es lo que se puede hacer sin rediseñar los dos
predictores. Y la respuesta añade `analyzed_tickets` y `truncated`, para que un
número acotado no se lea como completo. Los campos de antes siguen: no se cambia
el contrato.

Hay un test que **mide la pendiente** de consultas por ticket y falla si baja de
5: si alguien rediseña los predictores para que hagan una sola consulta, se pone
en rojo, y entonces hay que subir el tope — que es exactamente la conversación
que hay que tener en ese momento.

**Y el `except Exception` que se tragaba la mitad.** El bucle tenía
`except Exception: logger.debug(...)`, así que si los predictores fallaban para
la mitad de los tickets la respuesta salía igual, con la mitad de los datos y
sin decirlo. Sigue siendo *best-effort* —es lo correcto para una predicción—
pero ahora se cuenta en `failed_tickets`.

> **Un detalle del esquema que salió al escribir el experimento.** El filtro es
> `Ticket.status.notin_(["resolved", "closed"])`, con cadenas contra una columna
> `Enum(TicketStatus)`. Funciona porque `resolved` y `closed` **sí** son valores
> del enum, comprobado; pero es una comparación por texto contra un enum y no
> falla hasta que alguien escribe un valor que no existe — mi primer experimento
> creó tickets con `status="open"` y SQLAlchemy lo rechazó con
> `LookupError: 'open' is not among the defined enum values`. Los estados
> cerrados están ahora en una constante con nombre, `ESTADOS_CERRADOS`.

### Las traducciones del portal y los formularios dinámicos

Los otros dos ficheros de esta tanda **no traían defecto**, y conviene decirlo
tal cual: el filtro por organización ya estaba y era correcto en los dos, así
que ahí el trabajo fue mover y nada más.

* `client_portal.py`: las dos consultas de `OrgBranding.portal_translations` van
  a `branding_service.py`, junto al resto de la marca. Al moverlas se quitó una
  consulta redundante —la versión que escribí primero volvía a leer la fila que
  ya tenía en la mano, disparando el autoflush de la que acababa de añadir— y se
  añadió un aviso al registro cuando el JSON guardado es ilegible, que antes se
  tragaba en silencio.
* `service_desk/dynamic_forms.py`: **287 líneas** de ayudantes —las claves de
  `AppSetting`, el historial de configuración, el selector de opciones de
  contexto— a `dynamic_forms_service.py`. Los modelos Pydantic se quedan en el
  endpoint, que es donde tienen sentido: son el contrato de entrada de las
  rutas. El fichero pasa de 608 a 324 líneas y mantiene sus **10** rutas.

> **Y un aviso sobre el método, porque me pasó aquí.** El primer intento del
> movimiento de `dynamic_forms` cortó el bloque desde la primera clave hasta el
> primer `@router`, y **se llevó por delante los cinco modelos Pydantic** que
> estaban en medio. Lo cazó `ruff` al momento con catorce `F821`, no un test.
> La lección: al mover por rangos de líneas hay que comprobar qué hay *dentro*
> del rango, no sólo dónde empieza y dónde acaba — y las aserciones del script de
> movimiento tienen que decir tanto lo que el bloque **tiene** como lo que
> **no** debe tener.

## 3.octies El contador del #22 estaba mal, y tres defectos más de plantillas y activos

### Primero, la medición: el número que venía dando no era el que decía

El recuento del #22 se venía haciendo con un `grep` de `db.query`, `db.add`,
`db.commit`, `db.delete` y `db.flush` sobre `app/api/v1/endpoints/`. Y eso tiene
**tres** problemas, que se compensan entre sí y por eso no se veían:

1. **Cuenta las menciones en comentarios y docstrings.** En cuanto las tandas
   empezaron a documentar en el propio código lo que había antes —«esto hacía
   `db.query(Asset).all()`»— cada explicación escrita se contaba como un punto
   de acceso que sigue ahí. Lo noté al ver `assets.py` **subir** de 5 a 6
   después de quitarle dos consultas.
2. **No cuenta `db.execute`, `db.scalar`, `db.get`, `db.merge` ni `db.add_all`**,
   que son acceso a datos igual.
3. **Sólo mira `app/api/v1/endpoints/`**, así que `app/api/v1/routers/` quedaba
   fuera — y ahí hay acceso (`auth_core.py`, `auth_mfa.py`).

Ahora hay `scripts/audit_db_access_in_api.py`, que lo mide **por árbol de
sintaxis** sobre `app/api/` entera, así que sólo cuenta llamadas de verdad. Y
separa dos cosas que no son lo mismo:

* **acceso a datos** — `query`, `add`, `add_all`, `delete`, `flush`, `merge`,
  `execute`, `scalar`, `scalars`, `get`: lo que el hallazgo pide mover;
* **frontera de transacción** — `commit`, `rollback`, `begin`, `close` y
  también **`refresh`**: legítimo en el endpoint.

`refresh` está en el segundo grupo a propósito. No es una consulta que el
endpoint elija: es releer la fila que el servicio acaba de devolver para recoger
lo que pone la base (`id`, `created_at`, `server_default`), y va siempre pegado
a un `commit`. Contarlo como acceso infla el número con **44 llamadas**
—medidas— que no hay dónde mover: ponerlas en el servicio obligaría a que el
servicio confirme, que es lo contrario de lo que estas tandas hacen.

**Y con la regla nueva, medido sobre el histórico con `git worktree`:**

```
antes de la tanda 1 (collaboration)   257 puntos de acceso en 41 ficheros
al empezar hoy                         46 puntos en 23 ficheros
ahora                                  29 puntos en 18 ficheros
```

Las cifras viejas de este documento —«204», «95», «91», «82»— eran de la regla
vieja y **no son comparables** con éstas. No es que hubiera menos trabajo del
que decía: es que se estaba midiendo con una cinta métrica distinta en cada
punta. La cifra de referencia a partir de ahora es la del script.

### `templates.py`: la guarda que faltaba y un enum que no cabe en su columna

`endpoints/templates.py` tenía su propio `_get_template_or_404` que buscaba la
plantilla por id **sin ningún filtro de organización**, y de él colgaban las dos
altas: añadir un documento o un rol a la plantilla de otro cliente era una
escritura cruzada. Y las dos funciones de servicio que usa —`get_full_template`
y `export_project_as_template`— **no recibían al sujeto**, así que no podían
comprobar nada aunque quisieran: la misma forma que el endpoint de coste activo,
que sí lo recibía y lo descartaba con `_: User = Depends(...)`.

`export_project_as_template` además **no comprobaba de quién es el proyecto**.
Recibía `user_id`, una cadena, que no sirve para verificar nada. Cualquiera podía
exportar el proyecto de otro cliente y quedarse con los títulos de sus tareas y
sus riesgos.

**Y al arreglarlo salió el defecto que no buscaba.** La exportación escribía la
probabilidad con `str(getattr(r, "probability", "medium"))`, y
`Risk.probability` es un `Enum(RiskProbability)` **NOT NULL**, así que `str()` no
da `medium`: da `RiskProbability.medium`. Medido sobre los diez valores de los
dos enums:

```
str(RiskProbability.very_low)  -> RiskProbability.very_low    24 chars
str(RiskProbability.medium)    -> RiskProbability.medium      22 chars
str(RiskProbability.very_high) -> RiskProbability.very_high   25 chars
str(RiskImpact.negligible)     -> RiskImpact.negligible       21 chars
```

Y `template_risks.probability` es **VARCHAR(20)**. Son dos defectos:

1. **siempre** se guardaba un texto que ningún lector puede comparar contra el
   enum, así que la plantilla exportada salía con la probabilidad ilegible;
2. y en **cuatro de los diez valores** —entre ellos `medium`, que es el valor
   por defecto y el más frecuente— el texto **no cabe en la columna**: en
   PostgreSQL eso es `value too long for type character varying(20)` y la
   exportación entera revienta con un 500. **En SQLite se guarda truncado y en
   silencio, que es por lo que la suite no lo veía** — por eso el test nuevo
   comprueba la longitud explícitamente y no sólo el valor.

El `getattr(..., "medium")` tampoco hacía nada: la columna es NOT NULL, así que
el atributo está siempre. Y con él caían **cinco `hasattr` muertos** más
—`Project.project_type`, `Task.description`, `Task.estimated_hours`,
`Risk.category`, `Risk.mitigation_plan`—, todos comprobados como existentes. Lo
que hacían no era proteger: si alguna columna se renombrara, escribirían NULL en
silencio en vez de fallar.

**Y dos funciones muertas.** `add_template_document` y `add_template_role` ya
existían en el servicio, **no las llamaba nadie** —comprobado en `app/` y en
`tests/`— y tampoco filtraban por organización: el endpoint había
reimplementado lo mismo a mano. Dos implementaciones muertas de la misma cosa es
exactamente cómo aparecen las dos puertas de §3.septies, así que se deja una.

### `assets.py`: precisión sobre lo que era y lo que no

Las dos auditorías de activos —licencias y software— consultaban `Asset` **sin
filtro de organización**, y aquí hay que ser preciso:

* **En producción no era una fuga.** `SessionLocal` usa `TenantSession`, que
  sobrescribe `query()` y añade el filtro por `organization_id` —`Asset` tiene
  la columna—, así que el filtro estaba, sólo que implícito.
* **Pero era la única capa.** Y `asset_service.py` **no menciona
  `organization_id` ni una vez** en sus dieciocho funciones, así que no había
  nada detrás si esa capa falla. Ya falló una vez: el criterio rancio del §3.bis
  dejaba a cero a toda organización menos la primera del proceso.
  `/license-audit` devuelve `license_key`, que es una credencial.

**Lo que sí era un defecto sin mitigar es la carga.** `/software-audit` hacía
`db.query(Asset).all()` —**todos** los activos, como objetos del ORM, sin tope—
para acabar contando etiquetas. Ahora son dos consultas acotadas y la de
hardware trae **sólo la columna `tags`**. Hay un test que comprueba que ninguna
sentencia de activos sale sin `WHERE`, y que la de etiquetas no carga el activo
completo.

## 3.septies Dos marketplaces al mismo sitio, y un endpoint que no podía funcionar nunca

Los dos hallazgos salieron de mover a servicio
`endpoints/service_desk/connectors_marketplace.py` y
`endpoints/service_desk/cmdb.py`. Los dos ficheros quedan en **0** puntos de
acceso a base.

### Dos puertas al marketplace de integraciones, y ninguna era la buena en todo

`/api/v1/integrations/*` y `/api/v1/sd/connectors/*` instalan **la misma cosa**
—una `IntegrationInstance` sobre un `IntegrationConnector`— con dos
implementaciones escritas a mano por separado. Cada una era mejor en algo:

| | `integrations` | `service_desk` |
|---|---|---|
| valida `sync_direction`/`sync_frequency` | **sí** | no |
| cifra la configuración | **sí** | no la recibía |
| siembra el catálogo | **sí** | no |
| lista lo instalado sin N+1 | no (una consulta por instancia) | **sí** (`JOIN`) |

**El defecto con consecuencia es el de la configuración.** La puerta del Service
Desk no la recibía —`ConnectorInstallIn` no tenía el campo—, así que la
instancia se guardaba con `encrypted_config` a NULL. Quien la consume la lee
así, comprobado en `endpoints/salesforce_sync.py`:

```python
config = json.loads(decrypt_value(inst.encrypted_config) if inst.encrypted_config else "{}")
```

...y sin `instance_url` ni `access_token` responde **503 «credentials
incomplete»**. Y **no hay endpoint para rellenarla después**: la integración
quedaba instalada y muerta para siempre, sin error en ningún registro.

Los otros tres son menores pero de la misma clase: la puerta del Service Desk
aceptaba cualquier cadena como frecuencia de sincronización y la guardaba
(«cuando-pueda» incluido), y no sembraba el catálogo, así que en un despliegue
nuevo devolvía una lista vacía mientras la otra devolvía los seis conectores.

**Ahora las dos comparten** la lista blanca, el sembrado, la visibilidad del
conector y el cifrado, y el N+1 se arregla usando el `JOIN` que ya tenía la otra
—cada puerta aportó su mitad buena—. **La forma de las respuestas no cambia en
ninguna de las dos:** son API publicada, y el campo `config` que se añade es
opcional para no romper a quien ya llamaba sin él. Hay un test que cuenta las
sentencias emitidas: tres instalaciones cuestan **una** consulta, así que si el
N+1 vuelve se ve.

**Y una nota sobre el ámbito del catálogo.** Las dos puertas lo leían sin filtro
alguno. Hoy los conectores que trae el producto son globales y por tanto no
había fuga *medible* — pero `IntegrationConnector` tiene columna
`organization_id`, así que un conector privado es posible y entonces sí la
habría. El filtro es «los globales, más los propios», que es lo que ya declara
el modelo con `_tenant_filter_include_global` (§3.quinquies).

### `approve-baseline` no podía aprobar nada

`POST /cmdb/discovery/providers/{provider_id}/approve-baseline` buscaba así:

```python
db.query(CMDBItem).filter(CMDBItem.discovery_provider == provider_id)
```

Y `CMDBItem.discovery_provider` guarda el **tipo** de proveedor —`aws`,
`kubernetes`, `vsphere`; así lo escribe la reconciliación, con las constantes de
`services/cmdb/utils.py`—, mientras `provider_id` es el **UUID** de una fila de
`cmdb_discovery_providers`. Medido:

```
id del proveedor       1add5ac0-82a0-4d6c-812c-e2e1e46794a6
provider_type          aws
CI.discovery_provider  aws

consulta del endpoint (por id) ->  0 CIs
consulta por provider_type     ->  1 CI
```

Cero filas **siempre**, así que la respuesta era invariablemente
`{"ok": false, "error": "No CIs found..."}`. Es la misma clase de defecto que el
nodo «crear ticket» de los flujos de trabajo (§3.c): escrito, expuesto, con
respuesta de éxito prevista, y sin un solo camino que llegue a ella.

**Y el ámbito tampoco estaba.** No había ninguna comprobación de a quién
pertenece el proveedor, mientras su vecino `list_discovery_jobs` **sí** la hacía
y lo decía en un comentario. Con la consulta arreglada eso pasa de inocuo a una
**escritura cruzada entre clientes**: aprobar la línea base de los CIs de otro
cliente le limpia `drift_detected_at`, es decir **le apaga una alerta de
configuración**. Por eso el arreglo lleva las dos cosas juntas y no sólo la
consulta.

Los CIs se acotan además por organización, y hacía falta: los dos proveedores
del test son de tipo `aws`, así que filtrar sólo por `provider_type` habría
alcanzado los CIs de las dos organizaciones.

> **Una limitación que hay que saber, y no es un defecto del arreglo.** El CI
> sólo guarda el **tipo** de proveedor, no cuál de ellos lo descubrió. Si una
> organización tiene dos proveedores AWS, aprobar la línea base de uno aprueba
> también los CIs del otro. Distinguirlos exige una columna nueva en
> `cmdb_items` y volver a poblarla desde el descubrimiento: es un cambio de
> esquema con migración, no algo que se cuele en esta tanda. Está escrito en el
> docstring de `aprobar_linea_base`.

La comprobación del proveedor en el listado de jobs también se mueve **dentro**
del servicio. Es un movimiento y no un arreglo —el filtro ya estaba y era
correcto—, pero dentro no se puede olvidar al escribir el siguiente endpoint, y
olvidarla es exactamente lo que le pasó a `approve-baseline`.

## 3.sexies El Service Desk entero: la columna de tenant, la migración que erró el nombre de la tabla, y dos endpoints de IA sin ámbito

Salió al mover a servicio los cuatro puntos de acceso de
`endpoints/service_desk/tickets.py`. Son tres cosas distintas y conviene no
mezclarlas.

### 1. `sd_tickets.organization_id` no la rellenaba nadie

Es §3.quater otra vez, y con el alcance más grande de todos. Medido con la clase
de sesión real de la aplicación, no razonado:

```
usuario de ORG-A  ->  ['t-org']              (el ticket con organización)
usuario de ORG-B  ->  []
superadmin        ->  ['t-nulo', 't-org']
```

Y **ninguno de los seis sitios que crean tickets pone la columna**:
`ai_modules/voice`, `collaboration/bots`, `integrations`,
`public_forms_service`, `service_desk/asset_service` y
`service_desk/inbound_email_service`. Uno de ellos lleva además este comentario:

```python
# NOTA: Ticket no tiene columna organization_id; el scope multi-tenant
# viene vía project_id → Project.organization_id.
```

**Y sí la tiene.** Es el mismo comentario rancio que ya me hizo empeorar el
filtro de un trabajo de fondo, y aquí ha servido de justificación para no
rellenarla en el resto del módulo. Un comentario que afirma algo sobre el
esquema caduca cuando el esquema cambia, y nadie lo revisa.

### 2. Por qué las filas viejas sí tienen organización y las nuevas no

La **076** hizo el relleno original con una lista de nombres de tabla
adivinados por un script. Decía `tickets`, y la tabla real se llama
`sd_tickets`, así que **se la saltó** — la 076 salta en silencio las tablas que
no existen. La **080** lo arregló por introspección y rellenó `sd_tickets` con
la organización por defecto.

Es decir: **todo lo creado después de la 080 quedó en NULL**, y eso es el tráfico
normal de la aplicación desde entonces. El defecto no estaba en el diseño del
aislamiento; estaba en que el relleno fue puntual y la escritura nunca se
arregló.

### 3. La migración 093, y por qué no usa la organización por defecto

`093_tickets_backfill_organization` rellena `sd_tickets` heredando, en este
orden: quien lo creó, quien lo pidió, a quién está asignado, su proyecto, su
cliente, y el usuario de portal que lo pidió. Después rellena las **17 tablas
que cuelgan de un ticket** por `ticket_id` —la lista se comprobó contra
`Base.metadata`, son todas las que tienen a la vez `organization_id` y
`ticket_id`—.

**No usa la organización por defecto como respaldo, y eso es deliberado.** Es lo
que hicieron la 076 y la 080, y en un despliegue con varios clientes eso le
entrega al primero las filas de los demás. Un ticket sin ninguna de las seis
referencias se queda en NULL: no hay de dónde deducirlo, e inventarlo sería
peor que dejarlo.

Verificada ejecutando el `upgrade()` de verdad contra un escenario sembrado a
mano, once casos: las cinco herencias, la precedencia (el creador manda sobre el
proyecto), la fila que ya tenía organización y **no** se toca, la hija que
hereda del ticket, y la hija sin ticket que se queda como estaba. El mismo
escenario está en `tests/test_tickets_ia_por_tenant.py`, así que no depende de
que yo lo ejecutara una vez.

### 4. Los dos endpoints de IA que buscaban el ticket por id, sin más

`/tickets/{id}/routing-candidates` y `/tickets/{id}/ai-explain` hacían
`db.query(Ticket).filter(Ticket.id == ticket_id).first()`, mientras su vecino
`ticket_detail_payload` —en el mismo módulo de servicio— usa
`scope_ticket_query`. La asimetría de siempre: dos lecturas del mismo ticket por
id, una comprobada y la otra no.

**Y lo que se filtraba no era sólo el ticket.** `/ai-explain` devuelve la lista
de agentes candidatos con su puntuación, es decir **los nombres y el rendimiento
del equipo de soporte de otro cliente**, y cuelga de `get_current_user` a secas,
no de un rol de gestión.

Se usa `scope_ticket_query` y no un filtro por `organization_id`, y la razón hay
que retenerla: **`scope_ticket_query` restringe además a un empleado o
subcontratado a los tickets que pidió o tiene asignados**, así que filtrar por
`organization_id` a secas habría sido *más permisivo* que el listado y habría
dejado la lectura de uno suelto por detrás de la lectura de muchos.

La respuesta de `/ai-explain` mantiene su forma (`{"ok": false, ...}` en vez de
un 404). Es incoherente con todos sus vecinos y no lo consume nadie del
frontend, pero cambiarla de paso sería un cambio de contrato que este trabajo no
necesita. Queda anotado, no cambiado.

### 5. La guarda que estaba copiada tres veces

`get_scoped_ticket_or_404` existía **literalmente por triplicado** en
`ticket_update_service`, `comment_service` y `ticket_ops_service`, con una única
diferencia: dos de las copias lanzaban el 404 **sin texto**. Ahora vive en
`scoping.py`, junto a `scope_ticket_query`, que es de lo que depende, y las tres
la reexportan con el mismo nombre — así ningún sitio de llamada cambia. Al
separarla cayeron **seis imports muertos** que las tres copias mantenían vivos.

Hay un test que comprueba la **identidad del objeto**, no que el código sea
parecido: si alguien vuelve a escribir una copia local, se pone en rojo.

`tickets.py` queda en **0 puntos de acceso a base**, y las 2.029 rutas de la
aplicación siguen siendo idénticas.

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

### #18 complejidad — **cerrado**: ninguna función de `app/` por encima de 10

> **Estado hoy:** `python scripts/audit_complejidad.py` responde «Ninguna
> función de `app/` por encima de 10». Se llegó desde 94 / 253 / 17 (funciones
> por encima del umbral / exceso acumulado / máximo). El **cómo** está en
> §3.septvicies, y es la parte que importa: casi todas eran una tabla escrita
> como cascada de `if`, o el mismo bloque copiado dos, tres y hasta cuatro
> veces. Lo que sigue debajo es el registro de la primera mitad del trabajo.

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

> **Esta lista estaba desfasada y se corrige midiendo.** Decía
> `strictNullChecks` (226 errores) y `noImplicitAny` (387), y las dos están hoy
> en **cero**: `npm run typecheck:strict` cubre los 338 ficheros de `src/`,
> tests incluidos (§3.sexvicies). Decía también **3 moderate** en `npm audit`
> por `echarts` y `react-router-dom`; `npm audit` responde hoy **cero
> vulnerabilidades**, esas dos migraciones incluidas.

**Lo que queda abierto de verdad, medido hoy:**

> **Cerrado en §3.duotrigies.** Este punto decía que el control de rol estaba
> a parches en toda la capa API, y era verdad: contando **todas** las rutas de
> escritura —no sólo las que llaman a `enforce_abac`— había **563 sin ningún
> control de rol** frente a 603 que sí lo tenían. Hoy son **929 con guarda** y
> **115 exentas con motivo escrito y comprobado**, y un guardián de cuatro
> reglas impide que el número vuelva.
> **Cerrado en §3.untrigies: 0 de 1.852.** Este punto decía «traducción al
> 62,2 %, faltan 1.419 claves», y ya era falso cuando se escribió —eso se cerró
> en `d5295e6`—. Lo que sí quedaba era otra cosa: **1.852 cadenas escritas a
> pelo en el JSX**, que al no tener clave no le faltaban a ningún idioma y por
> eso ningún gate las veía. Hoy son **cero**, en los tres idiomas, y hay dos
> gates nuevos que lo sostienen.
>
> Y de camino salió una tercera cara del mismo hallazgo: **174 claves que el
> código pedía y que nadie había declarado nunca**, todas anteriores a este
> trabajo. No salían en blanco —el runtime humaniza la clave—, así que un
> usuario español leía «Add comment» y nadie lo reportaba.
> **Y el tercer punto de esta lista tampoco estaba abierto.** Decía «204
> `db.query()` / `db.commit()` en la capa API». La medición oficial —
> `python scripts/audit_db_access_in_api.py`, que cuenta por árbol de sintaxis
> sobre `app/api/` entera— responde hoy **0 puntos en 0 ficheros**, desde 257,
> y tiene guardián propio en `tests/test_capa_api_sin_acceso_a_base.py`, que
> importa el mismo script para que la regla no pueda divergir de la medida.
>
> Un `grep` ingenuo de `db.commit()` sigue devolviendo 48, y por ahí venía la
> confusión: son parte de las **109 fronteras de transacción** que quedan a
> propósito en el endpoint. Confirmar no es consultar, y moverlo al servicio
> sería lo contrario de lo que hicieron esas tandas.

> **Los tres puntos de esta sección estaban desfasados a la vez, y conviene
> decirlo entero.** Los tres describían trabajo ya hecho: la traducción se
> cerró en `d5295e6`, el acceso a datos llegó a cero en la tanda de
> `collaboration`, y las 24 rutas se cerraron en §3.trigies. Ninguno se
> actualizó aquí al cerrarse.
>
> La lección es la misma que recorre toda esta auditoría, aplicada al propio
> documento: **un número que nadie vuelve a medir envejece hacia el lado
> equivocado**. Los tres se detectaron al ir a trabajar en ellos y encontrarse
> el trabajo hecho — es decir, midiendo antes de actuar, que es lo único que ha
> funcionado aquí. Lo que queda abierto de verdad son las dos primeras entradas
> de esta lista, y las dos tienen ya un gate que las mide sola.

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

Queda **1 de 38** hallazgo en «parcial»: **#18 complejidad** — y lo que queda
de él ya no es «no se ha hecho», es **deuda medida con suelo puesto**: 94
funciones por encima de 10 → **74**, exceso 253 → **173**, máximo 17 → **16**,
con `scripts/audit_complejidad.py` y un trinquete que bloquea
(`tests/test_complejidad_no_empeora.py`). Veinte funciones salieron de la lista y **ninguna
por trocearla**: catorce escondían un defecto —incluido el dominio de tareas
implementado dos veces (§3.novodecies)— y las seis últimas tenían costura con
nombre propio (§3.quinvicies). Y un barrido por AST sobre las que quedan
confirma que **no esconden ninguna tabla de despacho**: son largas
y lineales, que es una razón distinta de «nadie las ha mirado».

**Lo que salió por debajo al registrar el filtro de tenant en la suite** —la
decisión que llevaba abierta toda la auditoría— está en **§3.vicies**, y no es
menor: el panel de sesiones activas llevaba tiempo vacío para todo el mundo, y
la bandera `bypass_tenant_filter` que documenta la salida de emergencia **sólo
la respetaba una de las tres capas de aislamiento**.

**Y el barrido de duplicación, que faltaba, ya está hecho** (§3.duovicies).
`scripts/audit_funciones_duplicadas.py` recorre `app/` por esqueleto de AST y
saca 31 parejas de funciones casi idénticas. **Se miraron una a una y ninguna es
un defecto**: cada una difiere exactamente en lo que debe. Es un resultado
negativo y por eso merece estar escrito — la duplicación había producido seis
hallazgos reales encontrados de casualidad, y ahora se sabe que no quedan más
por ese camino, al menos por encima de doce sentencias. Lo que sí salió fue una
consolidación (`_ticket_category`, escrita dos veces con la misma nota de
`FIX:`) y una deuda de diseño anotada: dieciocho copias del par
`_get_json`/`_set_json` sobre `AppSetting`, cinco sin `organization_id`, que se
aíslan por el nombre de la clave en vez de por la columna.

El **#22**
(acceso a base en la capa API) esta **cerrado**: de 257 puntos a 0, con guardian
de tolerancia cero. El **#37** (rutas del frontend que no existen) esta
**cerrado**: de 62 a 11 y de 11 a 0, con su constante en cero. **#37 remedido (§3.ter):
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

1. **#18: ya no hay una tanda dedicada que hacer.** `apply_filter` está hecha
   —es `_CLAUSULAS`— y con esta tanda se han ido las trece que escondían
   duplicación o una tabla de despacho. Lo que queda son **80 funciones largas
   pero lineales**, y para ellas el rendimiento decreciente es real y está
   medido: pártelas **cuando haya que tocar el fichero por otra razón**, no en
   una tanda. El orden por el que elegir está en
   `python scripts/audit_complejidad.py`, que `ci_local.sh` imprime como gate
   informativo.

   Lo que sí hay que respetar es el trinquete. Sus tres reglas y por qué falla
   también ante una mejora están en §3.octodecies; la que importa es la
   primera: **una función nueva no puede nacer por encima de 10, y meterla en
   `CONOCIDAS` para que pase no es una opción** — esa lista es la deuda que ya
   había, no un buzón.
2. **#22, los puntos de acceso a base en la capa API** — por dominios, no de
   golpe, cada tanda con su suite. **Tanda 1 cerrada:** `collaboration`, de 127
   puntos a 0 en ocho ficheros, con diez defectos destapados por el camino
   (§#22) y, al verificarlo, un **apagón de datos para toda organización que no
   fuera la primera del proceso** en el filtro de aislamiento (§3.bis).
   **CERRADO: 0 puntos de acceso en 0 ficheros**, medido con
   `scripts/audit_db_access_in_api.py`, mas 111 fronteras de transaccion, que no son acceso a datos
   y se tratan aparte. Con la misma regla, medido sobre el historico:
   **257 en 41 ficheros** antes de la tanda 1, **46 en 23** al empezar hoy.

   Las cifras viejas de este documento —204, 95, 91, 82— salian de un `grep` que
   contaba tambien las menciones en comentarios, no contaba `db.execute` ni
   `db.get`, y no miraba `app/api/v1/routers/`. **No son comparables** con
   estas; el porque esta en 3.octies. Cerrado **todo**: `collaboration` (127 -> 0), `tickets`, `performance`,
   `jira_integration`, `user_costs`, `baselines`, `branding`,
   `workflow_designer`, `governance_ops`, `smart_catalog`,
   `connectors_marketplace`, `cmdb`, `templates`, `assets`, `esign`,
   `client_portal`, `dynamic_forms`, `predictive`, `change_impact`, `scim`,
   `auth_core`, `auth_mfa`, `alert_correlation`, `semantic_engine`,
   `predictive_observability`, `bpmn_processes`, `bi_etl`, `bi_collaboration`,
   `bi_intelligence`, `billing_reports`, `invoices` y `backlog`.

   **No queda nada.** El detector da cero, y hay un guardian de tolerancia cero
   en `tests/test_capa_api_sin_acceso_a_base.py` que importa el propio script de
   medicion en vez de reimplementar la regla. El detalle del cierre esta en
   3.terdecies.

   Cerrados a 0: `collaboration` (8 ficheros), `tickets`,
   `connectors_marketplace`, `cmdb`, `templates`, `assets`, `esign`,
   `client_portal`, `dynamic_forms`, `performance`, `workflow_designer`,
   `user_costs`, `baselines`, `branding`, `jira_integration`,
   `governance_ops`, `smart_catalog` y `ai_auto_resolution`.

   `service_desk/predictive.py` **ya esta** (ver 3.novies): era el unico
   defecto localizado y sin arreglar de la lista. La orquestacion del trabajo de auto-resolucion (cerrojo,
   estado, tarea de fondo, registro del fallo) sigue en el endpoint: son
   fronteras de transaccion, no acceso a datos, asi que el contador nuevo ya
   no las suma con lo demas.
3. **Registrar el escuchador `do_orm_execute` en la factoría de sesiones de los
   tests — HECHO** (§3.sexdecies). `TestSession` usa `TenantSession` y tiene
   registrados el escuchador y el sellado. Era seguro por construcción y no se
   veía hasta ejecutarlo: las tres capas salen por la puerta de atrás cuando la
   sesión no está inicializada, así que un test que no autentica no cambia. La
   suite entera pasa **sin una sola excepción declarada**.
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
- **`echarts` 5→6 y `react-router-dom` 6→7: HECHAS** (2026-09-15), y resultaron
  mucho más baratas de lo que este documento suponía. Aquí decía «cada uno es
  una migración con riesgo sobre 119 rutas lazy», **sin haberlas intentado**.
  Costaron media hora entre las dos y `npm audit` quedó en **cero**.

  De `react-router` 6 a 7 **no hubo que cambiar ni una ruta**, y la razón merece
  quedar escrita: el proyecto ya declaraba `future={{ v7_startTransition,
  v7_relativeSplatPath }}` en el `BrowserRouter`, es decir, **ya corría con la
  semántica de la 7**. Lo único que cambió es que esas banderas son ahora el
  comportamiento por defecto y la prop desapareció. Y la aplicación sólo usa la
  API declarativa —`BrowserRouter`, `Routes`, `Route`, los hooks, `Link`,
  `NavLink`, `Navigate`—, ninguna de las de datos (`createBrowserRouter`,
  `loader`, `json`), que es donde estaban los cambios de verdad.

  `echarts` 5→6 tampoco pidió nada: `echarts-for-react` subió solo a 3.0.6 y el
  build salió en verde a la primera.

  **La lección, que es la reutilizable:** estimar el riesgo de una migración
  leyendo el número de versión es como contar `db.query` con `grep` — sale un
  número, y no es el que importa.

  **Corrección del 2 de septiembre:** el gate bloqueante está en nivel `high`, y
  cuando se escribió esto estaba a 0 — pero para entonces **ya había aparecido un
  `high` nuevo**: `browserslist`, transitiva vía `autoprefixer`, `@babel/core` y
  `webpack`. Arreglado con un salto de **parche** (4.28.2 → 4.28.8) tocando sólo
  el lockfile; `package.json` no cambia. Ahora `high` y `low` están a 0 y quedan
  los 3 `moderate`.

  Lo que hay que retener: **`npm audit` cambia sin que nadie toque el código.**
  Una frase como «está a 0» caduca sola. Conviene ejecutarlo antes de cada tanda,
  no confiar en lo que diga este documento.

  **Y volvió a pasar, el 15 de septiembre.** Sin un solo commit de código entre
  medias, el gate bloqueante estaba en rojo: **2 críticas y 1 alta**. La historia
  completa está en §3.unvicies; el resumen es que las críticas entraban por una
  librería de mapas que esta aplicación no usa, y que se fueron recortando el
  bundle en vez de subiendo de versión mayor.

  Ese mismo día se hicieron también las dos migraciones mayores que quedaban, y
  **`npm audit` está en cero**: 0 críticas, 0 altas, 0 moderadas, 0 bajas. Es la
  primera vez en toda la auditoría.
- **`strictNullChecks` (226) y `noImplicitAny` (387).** El camino es la whitelist
  de `tsconfig.strict.json`: añadir ficheros y dejar el gate verde.
