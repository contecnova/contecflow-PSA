# Del ticket al PR: agente de código que propone el arreglo como pull request

23-11-2026 · migración `203_ticket_a_pr` · módulo **opcional por empresa, apagado por defecto**.

Desde un ticket, un bug o una tarea, una persona con la capacidad adecuada lanza un agente de código contra el repositorio del cliente. El agente propone qué va a cambiar (plan de solo lectura), una persona lo aprueba, el agente aplica el cambio en un contenedor aislado, contecflow comprueba el diff y abre un pull request (GitHub) o un merge request (GitLab). El PR va unido a un cambio ITSM que pasa por el CAB: **el merge solo se habilita cuando el cambio está aprobado y lo hace siempre una persona. contecflow nunca fusiona.**

Referencia técnica: [OpenCode](https://opencode.ai) (licencia MIT), en su imagen Docker `ghcr.io/anomalyco/opencode:<versión>` y en modo no interactivo (`opencode run`). El código no depende de OpenCode: hay una interfaz propia, el «motor de agente de código», y OpenCode es el primer motor.

## 1. Flujo

```
Ticket / tarea ──► «Proponer arreglo con IA»  (ticket_pr.lanzar; módulo activo; repositorio del proyecto)
   │  repositorio + rama base + instrucción (generada del ticket con los datos personales ocultos; editable)
   ▼
PLAN    contenedor aislado, espacio de trabajo de SOLO LECTURA, permisos del agente: ni editar ni shell ni red
   │  plan + «FICHEROS:»  ──► una persona aprueba o rechaza (ticket_pr.aprobar_plan)
   ▼
BUILD   contenedor aislado, desde el MISMO commit (base_sha) que el plan
   │  diff comprobado: ficheros protegidos, secretos, enlaces, binarios, tamaño  ──► si falla: «Bloqueado»
   │  [tests del repositorio en otro contenedor, si la empresa lo pide]          ──► si fallan: «Bloqueado»
   ▼
PR      rama nueva contecflow/<ticket>-<id> creada por API (commit con los cambios) + PR/MR
   │  estado `contecflow/cab` = pending (GitLab: además «Draft:»)
   ▼
CAMBIO  cambio ITSM normal (o estándar si encaja en un modelo del catálogo) pedido por quien lanzó, enlazado
   │  al ticket y con el enlace al PR  ──► CAB (quien lanzó no vota el suyo)
   ▼
CAB aprueba → `contecflow/cab` = success (y GitLab quita «Draft:»)   ·   CAB rechaza/cancela → failure
   ▼
Una PERSONA fusiona en GitHub/GitLab. El estado del PR (fusionado/cerrado) vuelve a la ejecución.
```

Todo queda en el ticket o la tarea (panel «Del ticket al PR»): cada ejecución con su estado, la instrucción y el plan, quién lo decidió y cuándo, el motivo de un bloqueo o fallo, el resumen del diff, los tests, el PR y su estado de merge, el cambio y su estado, las horas del agente, los tokens y el coste de IA, y el log del contenedor (con los datos personales ocultos).

Estados de una ejecución: `queued_plan` → `planning` → `awaiting_approval` → (`rejected`) → `queued_build` → `building` → (`blocked` | `failed`) → `awaiting_cab` → `cab_approved` → `merged`; además `cab_rejected`, `closed` y `cancelled`.

## 2. Diseño

| Pieza | Fichero | Qué hace |
|---|---|---|
| Modelo | `app/models/ticket_a_pr.py` | `ticket_pr_repos` (repositorios permitidos por proyecto) y `ticket_pr_runs` (ejecuciones) |
| Configuración | `app/services/ticket_a_pr/config.py` | Encendido (módulo `ticket_pr` de la gobernanza de IA), ajustes de la empresa (`app_settings` `ticket_pr.config`) sobre los `TICKET_PR_*`, credenciales cifradas (proveedor `ticket_pr` del almacén de integraciones) |
| Motor | `app/services/ticket_a_pr/motor.py` | Interfaz `MotorDeAgente` (`planificar`, `construir`, `ejecutar_tests`), registro `MOTORES` y `MotorSimulado` (tests) |
| OpenCode | `app/services/ticket_a_pr/opencode.py` | Primer motor: configuración y permisos de OpenCode, variables del modelo, lectura de eventos (texto, tokens, coste) |
| Aislamiento | `app/services/ticket_a_pr/sandbox.py` | Contenedor efímero por fase, red interna con proxy de salida con lista blanca, límites y limpieza |
| Git | `app/services/ticket_a_pr/git_clientes.py` | Interfaz `ClienteGit`; GitHub App (token de instalación de alcance mínimo) y GitLab (token de proyecto); `ClienteGitSimulado` (tests) |
| Diff | `app/services/ticket_a_pr/diff.py` | Árboles en memoria desde tar, ignorados, comparación, ficheros protegidos, detector de secretos, límites |
| Instrucción | `app/services/ticket_a_pr/instruccion.py` | Instrucción desde el ticket con los datos personales ocultos; plantillas |
| Flujo | `app/services/ticket_a_pr/servicio.py` | Lanzar, PLAN, aprobación, BUILD, PR, cambio, CAB, sincronización, cancelación, límites, coste, auditoría |
| Prueba | `app/services/ticket_a_pr/prueba.py` | Prueba de conexión real con `verificado` |
| API | `app/api/v1/endpoints/ticket_a_pr.py` | `/api/v1/ticket-pr/...` |
| Pantalla | `frontend/src/components/ticket-a-pr/` | `PanelTicketAPr` (ticket y tarea) y `ConfigTicketAPr` (`/settings/ticket-a-pr`) |

Decisión importante: **el código se baja y el PR se abre desde el servidor, por la API de GitHub/GitLab**, no desde el contenedor. El agente recibe el árbol de ficheros (sin `.git`) y devuelve el árbol cambiado; contecflow calcula el diff, lo comprueba y crea la rama con un commit por API. Así el contenedor **nunca ve una credencial de Git**, no necesita salida al host Git y no puede empujar a ninguna rama.

Las fases PLAN y BUILD corren en el worker (Celery, `segundo_plano.encolar`; en la lista blanca `FUNCIONES_ENCOLABLES`). Sin cola (sin Redis) corren dentro de la petición, como el resto de trabajos encolables. Un trabajo periódico (`app.worker.ticket_pr_sincronizar`, cada 5 min) lleva el estado del cambio al PR y pasa a fallo las ejecuciones colgadas más de 5 h.

## 3. Aislamiento y seguridad

OpenCode ejecuta órdenes de shell con todos los permisos de quien lo arranca y su análisis de órdenes es aproximado; el código del repositorio del cliente tampoco es de fiar (los tests lo ejecutan). Por eso:

- **Un contenedor efímero por fase** (plan, build, tests), destruido siempre al terminar (`docker rm -f`, red y volumen borrados en `finally`).
- **Sin red interna**: red Docker `--internal` propia. La única salida es un proxy squid en otro contenedor (`TICKET_PR_EGRESS_PROXY_IMAGE`) que solo acepta `CONNECT` a la **lista blanca**: el host de la API del modelo configurado, los que el motor necesita al arrancar (`TICKET_PR_ENGINE_EGRESS_HOSTS`) y los que añada la empresa (registros de paquetes). El host Git no está en la lista (no hace falta). Los tests, sin el host del modelo.
- **Sin secretos de la plataforma**: no se monta nada del host. El espacio de trabajo es un volumen propio que se rellena por la entrada estándar (tar) con un contenedor auxiliar sin red, y se vacía por la salida estándar. La clave del modelo va en un `--env-file` temporal (0600) que se borra en cuanto se crea el contenedor. Los ficheros `.env`, claves y certificados del repositorio **no se copian** al contenedor.
- **Usuario sin privilegios** (1000:1000), `--cap-drop ALL`, `no-new-privileges`, **raíz de solo lectura** (`--read-only`, `/tmp` y `HOME` en tmpfs); en PLAN, además, el espacio de trabajo es de solo lectura.
- **Límites** de CPU, memoria (sin swap), procesos y tiempo (al pasarlo, `docker kill`): `TICKET_PR_CPUS`, `TICKET_PR_MEMORY_MB`, `TICKET_PR_PIDS_LIMIT`, `TICKET_PR_PLAN_TIMEOUT_MIN`, `TICKET_PR_BUILD_TIMEOUT_MIN` (la empresa puede ajustarlos dentro de rangos).
- **Permisos del agente** (OpenCode `permission`): denegar por defecto. PLAN: `edit` y `bash` denegados. BUILD: `edit` permitido; `bash` denegado salvo las órdenes que liste la empresa; siempre denegados `webfetch`, `websearch`, `external_directory` y leer `.env`, claves y certificados. Nada en «ask».
- **Credenciales Git temporales y de alcance mínimo**: GitHub App con un **token de instalación por ejecución (1 h), limitado a ese repositorio** y a `contents: write`, `pull_requests: write`, `statuses: write`. GitLab: token de proyecto (Developer, `api`). contecflow solo crea ramas nuevas `contecflow/...` (si ya existe, falla) y nunca escribe en la rama base. **La rama protegida la protege el proveedor**: hay que configurar sus reglas (ver §6).
- **Comprobación del diff antes de abrir el PR** (`diff.comprobar`), en este orden: enlaces simbólicos o rutas raras creadas por el agente, sin cambios, nº de ficheros, **ficheros protegidos** (de fábrica: CI de GitHub/GitLab/Circle/Jenkins/Azure/Bitbucket/Travis/Drone/Buildkite, `CODEOWNERS`, `.env*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.jks`, `id_rsa*`, `**/secrets/**`, `*.tfvars`, `.npmrc`, `.pypirc`, `.netrc`, `.git/**`, `.gitmodules`; más los de la empresa), binarios, tamaño del diff y **secretos añadidos** (detector simple: claves privadas, AWS, GitHub, GitLab, Slack, Google, Stripe, Anthropic, OpenAI, claves de contecflow, JWT, credenciales en URL, asignaciones `password = "..."` y **la propia clave del modelo**). Los artefactos (`node_modules`, `__pycache__`, `dist`, lo del `.gitignore`…) nuevos no cuentan.
- **Límites por empresa y día** (UTC): ejecuciones (`TICKET_PR_MAX_RUNS_PER_DAY`), coste (`TICKET_PR_MAX_COST_PER_DAY_USD`), a la vez (`TICKET_PR_MAX_CONCURRENT`) y el tope diario de IA de la empresa (`AI_DAILY_BUDGET_USD`).
- **Sin Docker no se ejecuta nada en el host**: lanzar y aprobar responden 409 `ticket_pr_docker_no_disponible`, y el propio `sandbox.ejecutar` se niega.
- **Versión del motor fijada**: sin versión o con `latest`, 409 `ticket_pr_version_sin_fijar`.
- Las credenciales delegadas (claves de API, tokens OAuth) **no abren** `/api/v1/ticket-pr/` (`RUTAS_VEDADAS`): hace falta una sesión de una persona.

## 4. Permisos (capacidades literales)

| Capacidad | Roles por defecto | Qué abre |
|---|---|---|
| `ticket_pr.ver` | internos | Panel del ticket o tarea (solo de orígenes que ya ve), ejecución y log |
| `ticket_pr.lanzar` | admin, pm, team_lead | Proponer la instrucción, lanzar, cancelar, sincronizar con el CAB |
| `ticket_pr.aprobar_plan` | admin, pm, team_lead | Aprobar o rechazar el plan |
| `ticket_pr.config` | admin | Configuración, repositorios, prueba de conexión, coste por proyecto |

La visibilidad del origen manda: una ejecución se ve si se ve su ticket (`scope_ticket_query`) o su tarea (proyectos visibles); fuera, 404. Todo va acotado por empresa (TenantSession, RLS y filtros explícitos). La empresa puede exigir que el plan lo apruebe **otra persona** (`plan_requires_other_person`). En el CAB la segregación ya está: el cambio lo pide quien lanzó y el CAB no le deja votar el suyo.

## 5. Configuración (`/settings/ticket-a-pr`, capacidad `ticket_pr.config`)

- **Módulo**: encender o apagar (módulo `ticket_pr` de *Gobernanza IA → Módulos*; sin fila, apagado). Uso de hoy.
- **Motor y modelo**: motor (`opencode`), imagen y **versión fijada** (o `sha256:…`); proveedor de IA (el de la empresa por defecto o uno elegido) y modelo (vacío: el del proveedor).
- **Credenciales Git** (cifradas; se escriben, nunca se leen): `github_app_id`, `github_installation_id`, `github_private_key`, `github_api_url`, `gitlab_base_url`, `gitlab_token` (`PUT /settings/integrations/ticket_pr/{campo}`, auditado en `settings_audit`). Sin respaldo global: cada empresa las suyas.
- **Repositorios permitidos por proyecto**: proveedor, `owner/repo` (o ruta del proyecto de GitLab), rama base por defecto y orden de tests.
- **Seguridad**: ficheros protegidos adicionales, salida extra (hosts), órdenes de shell permitidas, ejecutar tests y bloquear si fallan, plan por otra persona, tipo de cambio (`normal` o `standard_if_fits` con el id del modelo del catálogo).
- **Límites** (en rangos) y **plantillas de instrucción** (marcadores `{repo}`, `{rama}`, `{tipo}`, `{codigo}`, `{titulo}`, `{descripcion}`; en build, `{instruccion}` y `{plan}`).
- **Prueba de conexión** y **coste por proyecto** (30 días).

Valores de la plataforma (`.env`, README «Runtime settings»): `TICKET_PR_ENGINE_IMAGE`, `TICKET_PR_ENGINE_VERSION`, `TICKET_PR_ENGINE_EGRESS_HOSTS`, `TICKET_PR_EGRESS_PROXY_IMAGE`, `TICKET_PR_HELPER_IMAGE`, `TICKET_PR_DOCKER_BIN`, `TICKET_PR_CPUS`, `TICKET_PR_MEMORY_MB`, `TICKET_PR_PIDS_LIMIT`, `TICKET_PR_PLAN_TIMEOUT_MIN`, `TICKET_PR_BUILD_TIMEOUT_MIN`, `TICKET_PR_MAX_RUNS_PER_DAY`, `TICKET_PR_MAX_COST_PER_DAY_USD`, `TICKET_PR_MAX_CONCURRENT`, `TICKET_PR_MAX_REPO_MB`, `TICKET_PR_MAX_CHANGED_FILES`, `TICKET_PR_MAX_DIFF_KB`.

## 6. Preparar GitHub o GitLab (lo hace el cliente)

**GitHub**

1. Crear una GitHub App de la organización con permisos de repositorio **Contents: Read & write**, **Pull requests: Read & write**, **Commit statuses: Read & write** (nada más) y sin webhook.
2. Instalarla **solo** en los repositorios que se van a permitir. Copiar el App ID, el Installation ID y generar la clave privada (PEM).
3. En la rama base (p. ej. `main`), una regla de protección: **Require status checks to pass → `contecflow/cab`**, **Require a pull request before merging** (con revisión), sin permitir a la App saltárselas. Así el merge solo se habilita cuando el CAB aprueba.

**GitLab**

1. Token de acceso de proyecto con rol **Developer** y alcance `api` (caducidad corta).
2. Rama base protegida: *Allowed to push: No one* (o Maintainers), *Allowed to merge: Maintainers*.
3. En *Settings → Merge requests*: **Pipelines must succeed**. contecflow publica el estado `contecflow/cab` como estado de commit y abre el MR como «Draft:», que GitLab no deja fusionar hasta que contecflow lo quita al aprobarse el cambio.

## 7. GRC

- **Auditoría** (`audit_log`, recurso `ticket_pr_run`, canal `ticket_pr`, con empresa, origen, proyecto y repositorio): `TICKET_PR_LAUNCH`, `TICKET_PR_PLAN_APPROVE`, `TICKET_PR_PLAN_REJECT`, `TICKET_PR_BLOCKED`, `TICKET_PR_FAILED`, `TICKET_PR_PR_OPENED`, `TICKET_PR_CHANGE_LINKED`, `TICKET_PR_CAB_SYNC`, `TICKET_PR_CANCEL`. Configuración: `UPDATE ticket_pr_config`, `UPDATE ticket_pr_module`, `CREATE/UPDATE/DELETE ticket_pr_repo`; credenciales en `settings_audit` (hash del cifrado).
- **Retención y bloqueo legal**: tipo `ticket_pr_runs` (`app/db/bloqueo_legal.py`): cuenta desde que la ejecución termina, solo las terminadas; se bloquea por ejecución, por quien la lanzó, por ticket, tarea o proyecto. El log del contenedor vive en la propia ejecución (`log_redacted`), así que se retiene y se bloquea con ella.
- **Datos personales**: la instrucción solo usa título, descripción, tipo y código del origen (nunca solicitante, correo, teléfono, cliente ni comentarios) y pasa por el detector de la gobernanza de IA (`redact_pii`) y la redacción de las políticas de la empresa; lo que se edita a mano se vuelve a ocultar al lanzar. El plan, el razonamiento y el log se ocultan antes de guardarse; la clave del modelo se borra del log. La descripción del PR (que sale de la plataforma) no lleva nombres de personas. Las referencias a personas (`launched_by`…) se quedan en nulo si la persona se suprime.
- **Segregación**: quien lanza no vota su cambio en el CAB (lo garantiza el CAB); opcionalmente, tampoco aprueba su plan.
- **Coste de IA**: cada fase apunta tokens y coste en `ai_usage_logs` (módulo `ticket_pr`, cuenta para el tope diario de la empresa) y en la ejecución, que lleva `project_id`: **coste imputado al proyecto** (`GET /ticket-pr/costes`). Las horas del agente son el tiempo de contenedor (`agent_seconds`).

## 8. Qué NO hace

- **No fusiona nunca.** Ni con el CAB aprobado: lo hace una persona en GitHub/GitLab.
- No escribe en la rama base ni reescribe ramas: solo crea `contecflow/<ticket>-<id>` nuevas.
- No ejecuta nada en el host: sin Docker, no hay agente.
- No toca la CI, los secretos ni los ficheros protegidos: si el agente lo intenta, el PR no se abre.
- No da al agente credenciales de Git ni acceso a la red interna o de la plataforma.
- No manda al modelo datos personales del ticket (lo que el detector reconoce; ver riesgos).
- No funciona con credenciales delegadas (API keys, tokens OAuth).
- No cancela un contenedor que ya está corriendo: la cancelación marca la ejecución y su resultado se descarta al terminar la fase (o al agotar su tiempo).

## 9. Riesgos y controles

| Riesgo | Control | Riesgo que queda |
|---|---|---|
| El agente ejecuta órdenes peligrosas | Contenedor efímero, sin privilegios, raíz de solo lectura, sin red salvo lista blanca; shell denegado por defecto | Fallos del aislamiento de Docker (núcleo compartido). Para más aislamiento: runtime gVisor/Kata (`--runtime`), por verificar |
| Exfiltración de código o de la clave del modelo | Solo sale a la API del modelo y a los hosts permitidos; el log oculta la clave | El agente podría mandar código al proveedor del modelo (es su función) o a un registro de paquetes permitido. Usar una clave dedicada con tope de gasto |
| Prompt injection desde el repositorio o el ticket | Plan revisado por una persona; diff comprobado; PR revisado y CAB | Un cambio malicioso sutil que pase la revisión humana |
| Secretos en el PR | Detector de patrones + clave del modelo + ficheros protegidos | Secretos con formatos no conocidos |
| Tocar CI o despliegue | Ficheros protegidos (de fábrica y de la empresa) | Configuraciones de despliegue en rutas no protegidas: añadirlas en Configuración |
| Merge sin CAB | Estado `contecflow/cab` + reglas de la rama en el proveedor; Draft en GitLab | Si el cliente no configura la protección de rama, el estado no bloquea |
| Coste descontrolado | Límites diarios de ejecuciones y coste, concurrencia, tope de IA de la empresa, tiempo máximo | El coste de una fase en curso se apunta al terminar |
| Datos personales al modelo | Solo título y descripción, detector + políticas, re-ocultado | Lo que el detector no reconoce (nombres en texto libre, p. ej.) |
| Imagen manipulada | Versión fijada (mejor digest `sha256:`) | La confianza en el registro de la imagen |

## 10. Prueba de conexión (`POST /ticket-pr/prueba` o Configuración → Probar)

Real, sin lanzar ningún agente: `docker` (el demonio responde), `imagen_motor`, `imagen_proxy`, `imagen_ayudante` (`docker pull` de las imágenes fijadas), `git` (credencial válida y, si hay un repositorio permitido de ese proveedor, acceso a él: en GitHub un token de instalación limitado a ese repositorio), `modelo` (el proveedor de IA responde con su clave). Cada una `true`, `false` o `null` (no aplica). `verificado`: `credencial_y_uso` si todo pasa y se ha probado un repositorio; `credencial` si Git y el modelo pasan pero falta Docker o un repositorio; `nada` si no. También responde a `POST /settings/integrations/ticket_pr/test` (ver `docs/integraciones/pruebas_de_conexion.md`).

## 11. Lo que queda por verificar con Docker, credenciales Git y un modelo reales

Aquí no hay Docker arrancado, ni credenciales Git, ni modelo: el flujo está probado con `MotorSimulado` y `ClienteGitSimulado`, y las órdenes de Docker y la configuración de OpenCode con tests puros. Queda por confirmar:

1. **OpenCode** en la versión que se fije: que `opencode run --agent plan|build --format json --model <p>/<m> "<instrucción>"` funciona dentro de la imagen como `ENTRYPOINT`; que lee `OPENCODE_CONFIG_CONTENT`; los nombres exactos de las claves de `permission` (`edit`, `bash`, `webfetch`, `websearch`, `external_directory`, `doom_loop`, `read`) y que «deny» corta de verdad; la forma de los eventos JSON (texto final, `tokens`, `cost`); y qué hosts necesita al arrancar (por defecto `models.dev` y `registry.npmjs.org`, `TICKET_PR_ENGINE_EGRESS_HOSTS`).
2. **Docker**: que el proxy squid (`TICKET_PR_EGRESS_PROXY_IMAGE`, `ubuntu/squid:6.6-24.04_beta`) arranca con `--cap-drop ALL` + `SETUID/SETGID`, `pid_filename none` y la configuración por variable; que el agente sale solo por él (`HTTPS_PROXY`) y que todo lo demás falla; que el contenedor auxiliar (`busybox:1.36.1`) rellena y vacía el volumen; que el usuario 1000 puede escribir en `/workspace` y que la imagen del motor arranca con `--read-only` y `HOME` en tmpfs; la limpieza en todos los caminos (también con el worker caído: contenedores con la etiqueta `contecflow.ticket_pr=1`).
3. **GitHub**: token de instalación con `repositories` + `permissions`; descarga del `tarball` (redirección a `codeload.github.com`, validada por el guardia SSRF); blobs/árbol/commit/ref; PR; estado `contecflow/cab`; que la regla de la rama bloquea el merge hasta `success`. Para GitHub Enterprise, `github_api_url`.
4. **GitLab**: `repository/archive.tar.gz?sha=`, API de commits con `start_sha` y `execute_filemode`, MR «Draft:», `statuses` con `name`, y que «Pipelines must succeed» + Draft bloquean el merge; `personal_access_tokens/self` con un token de proyecto en la prueba.
5. **Modelo**: proveedores Anthropic, OpenAI, Google, DeepSeek, Groq, Mistral (nativos en OpenCode) y Azure/Ollama como compatibles con OpenAI (`@ai-sdk/openai-compatible`, que OpenCode instala de npm); Ollama local necesita su host en `OUTBOUND_PRIVATE_HOSTS_ALLOWED` y en la lista blanca.
6. **Rendimiento**: repositorios grandes (`TICKET_PR_MAX_REPO_MB`), tiempos y memoria reales del agente y de los tests.

## 12. Tests

`tests/test_ticket_a_pr.py` (sin Docker, Git ni modelo): módulo apagado por defecto, sin Docker no se ejecuta, versión fijada, capacidades, credencial delegada vetada, flujo plan → aprobación → build → PR → cambio → CAB (aprueba y rechaza), sin CAB el PR queda pendiente, plan rechazado, plan por otra persona, cancelación, bloqueos (protegidos de fábrica y de la empresa, `.env`, secretos, la clave del modelo, enlaces, binarios, sin cambios, tests que fallan), ignorados, límites diarios de ejecuciones y coste, aislamiento por empresa, repositorio de otro proyecto, datos personales ocultos, configuración auditada y sin secretos, retención, y piezas puras (globs, detector de secretos, rutas del tar, órdenes de Docker, configuración de OpenCode, estado del PR según el cambio).
