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

# Suite completa de backend. SIEMPRE con -n auto: en serie tarda MAS DE 90
# MINUTOS y no cabe en ningun timeout razonable. `scripts/ci_local.sh` ya la
# invoca asi; ejecutarla en serie fue una perdida de tiempo evitable.
./.venv/Scripts/python.exe -m pytest tests -q --no-header -p no:cacheprovider -n auto

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

### #18 complejidad — parcial

Hecho, las cinco peores (dejando aparte `seed`, que es generación de datos de
demostración):

| Función | Antes | Ahora | Verificación |
|---|---|---|---|
| `_fetch_metric_series` (`bi_smart_alerts/metrics.py`) | **247** en 945 líneas | peor caso 27 | 133 series a JSON, idénticas |
| `execute_actions` (`automations_service.py`) | 38 en 218 líneas | 13 | 37 tests existentes |
| `validate_graph` (`workflow_designer_service.py`) | 42 en 157 líneas | bajo umbral | 38 grafos, salidas idénticas |
| `collaboration_ws` (`endpoints/collaboration/ws.py`) | 39 en 176 líneas | bajo umbral | **23 tests nuevos** (tenía cero) |
| `apply_routing_rules` (`routing_rule_service.py`) | 35 en 105 líneas | bajo umbral | 62 casos + **59 tests nuevos** (tenía cero) |

Dos de ellas **no tenían un solo test** antes de tocarlas, y en ambos casos eso
era un hallazgo por sí mismo:

- El manejo de mensajes del **chat en tiempo real** sólo existía dentro del
  `async def` del endpoint y ningún test abría el socket. Cada rama del despacho
  de tipos, el control de caudal y la revalidación de acceso eran código en
  producción que nadie había ejecutado en una prueba. Ahora son métodos de
  `_ConexionColab` y se prueban con dobles.
- `apply_routing_rules` decide **a qué grupo y con qué prioridad llega cada
  ticket** que entra. Un error ahí manda el trabajo al equipo equivocado sin que
  nada falle.

Detalles que el método verbatim cazó y que a mano se habrían escapado:

- dos `continue` que pertenecían al bucle **exterior** de acciones (medido por
  AST: profundidad de bucles 0) y que dentro de un manejador debían ser `return`;
- el parámetro de contexto no podía llamarse `c`, porque el original asigna a `c`
  en una rama y lo usa como variable de comprensión en cuatro más;
- en `validate_graph`, **el orden de los mensajes es parte del contrato** (la
  interfaz los presenta en lista), de ahí que errores y avisos se pasen por
  parámetro en lugar de devolverse.

Método usado, y conviene repetirlo: **extracción verbatim con un script**, no
reescritura a mano. Las 945 líneas son cálculo de métricas de negocio; el script
mueve cada rama con su condición, su cuerpo y sus comentarios, y sólo añade el
preámbulo que reenlaza los nombres del entorno. **La equivalencia se verificó
volcando las 133 series del catálogo a JSON antes y después: idénticas valor a
valor.** Los scripts están en el directorio de trabajo temporal, pero el método
está descrito en las cabeceras de los módulos resultantes.

Dos cosas que el `compile()` del script cazó y que a mano se habrían escapado:
- dos `continue` que pertenecían al bucle **exterior** de acciones (comprobado
  por AST midiendo la profundidad de bucles: 0 en ambos casos) y que dentro de
  un manejador tenían que ser `return`;
- el parámetro de contexto no podía llamarse `c`, porque el código original
  asigna a `c` en la rama de `task_completion_rate` y lo usa como variable de
  comprensión en cuatro más. Se llama `ctx`, que no aparece ni una vez en el
  original.

**Pendiente, con la métrica honesta:** el *recuento* de funciones sobre el
umbral es **137**, frente a las 138 del inicio — apenas se mueve, porque partir
una función grande produce varias medianas. La métrica que importa es el **exceso
total sobre 10, que bajó de 1.023 a 712 (−30 %)**. Las siguientes por orden de
valor:

| Complejidad | Función | Fichero | Nota |
|---|---|---|---|
| 67 | `seed` | `db/seed_parts/core.py` | datos de demostración, valor bajo |
| 34 | `build_tenant_context` | `ai_chat/context_service.py` | **525 líneas**, ~20 secciones independientes; sin tests |
| 32 | `sso_callback` | `api/v1/routers/auth_sso.py` | tiene tests (PKCE/nonce) |
| 29 | `lifespan` | `app/main.py` | arranque; cuidado, no es puro |
| 29 | `apply_ticket_update` | `service_desk/ticket_update_service.py` | |
| 27 | `_serie_cost_profile` | `bi_smart_alerts/metrics.py` | ya cubierta por el catálogo |

`build_tenant_context` es la más grande que queda: construye ~20 secciones de
contexto para el asistente, cada una con su consulta, filtro de organización,
filtro de alcance y transformación a diccionarios. La descomposición natural es
una función por sección más un objeto de alcance (db, org_id, user,
user_project_ids, banderas de permiso, now). **Es código de sólo lectura**: un
error degrada las respuestas del asistente, no corrompe datos. Golden-master
aplicable con las fixtures de test.

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
**190 `db.query()` y 108 `db.commit()`** de la capa API. Son 298 puntos donde un
endpoint habla con la base sin pasar por un servicio. Moverlos es trabajo grande
y de riesgo real sobre código en producción: hacerlo **por dominios, no de
golpe**, cada tanda con su suite.

### Otros pendientes con riesgo propio

- `strictNullChecks` (226 errores) y `noImplicitAny` (387).
- `echarts` 5→6 y `react-router-dom` 6→7: son los **3 moderate** que quedan en
  `npm audit`. Cada uno es una migración con riesgo real sobre las 119 rutas
  lazy, así que están medidos y no forzados. El gate bloqueante está en nivel
  `high`, que está a 0.

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

## 5. Patrón que atraviesa toda la auditoría

Conviene tenerlo presente al seguir: el fallo dominante de este código **no** es
código ausente, es **controles escritos, con interfaz, con tests que pasan, y
conectados a nada**. Cinco casos confirmados:

1. `ABACMiddleware` — nunca se ejecutó.
2. `ABAC_COVERED_PREFIXES` — 45 de 110 prefijos con cero llamadas a
   `enforce_abac`. Cobertura «aspiracional».
3. `/analytics/adhoc` — `hasattr` sobre una función inexistente, devolvía
   siempre `results: []`.
4. La matriz de permisos GRC — `check_permission()` con cero invocaciones; sólo
   su propia pantalla leía la tabla.
5. El reconocimiento ASC 606 de T&M — `getattr` a dos campos inexistentes,
   cero euros siempre.

Los cinco comparten mecanismo: **un acceso tolerante (`getattr`/`hasattr` con
defecto, o un `except` que degrada) convirtiendo un error de programación en un
resultado vacío plausible.** Al revisar código nuevo aquí, ese es el patrón a
buscar.

---

## 6. Ficheros clave añadidos o reescritos

```
app/core/deps.py                    require_superadmin (no existía)
app/core/tenancy.py                 guarda estricta de org_id del cliente
app/db/session.py                   filtro de tenant fail-closed + TenantIsolationError
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

---

## 7. Orden sugerido para continuar

Quedan **3 de 29** hallazgos en «parcial», y ninguno es un fallo latente: son
deuda medida. Nada de lo que queda corrompe datos ni abre un agujero.

1. **`build_tenant_context`** (#18) — 525 líneas, complejidad 34, ~20 secciones
   de contexto independientes y **sin tests**. Es la mayor que queda con valor
   real, y el método de extracción verbatim ya está probado cinco veces. Es
   código de sólo lectura: un error degrada las respuestas del asistente, no
   corrompe datos. Golden-master aplicable con las fixtures.
2. **#22, los 298 puntos de acceso a base en la capa API** — por dominios, no de
   golpe, cada tanda con su suite.
3. **#16, traducción** — en lotes revisables, **subiendo `COBERTURA_MINIMA` en
   `check_i18n_coverage.mjs` en cada lote**.

Lo demás yo lo dejaría donde está, y digo por qué:

- **Consolidar las cuatro librerías de gráficos en una.** El coste de carga ya
  está resuelto (#19: −68 % al abrir las páginas afectadas), así que migrar 25
  usos de echarts y 18 de recharts es riesgo alto por beneficio hoy marginal.
- **`echarts` 5→6 y `react-router-dom` 6→7** — los 3 avisos `moderate` de
  `npm audit`. Cada uno es una migración con riesgo sobre 119 rutas lazy. El gate
  bloqueante está en nivel `high`, que está a 0.
- **`strictNullChecks` (226) y `noImplicitAny` (387).** El camino es la whitelist
  de `tsconfig.strict.json`: añadir ficheros y dejar el gate verde.
