# Motor de aprobaciones

Referencia breve del motor de aprobaciones tal como está en el código (revisado
el 2026-11-16). La versión anterior de este documento (mayo 2026) describía una
máquina de estados `DRAFT/PENDING/EXPIRED/ARCHIVED`, modelos `ApprovalVote` y
tipos `sequential/quorum/any` que **no existen**; queda sustituida por esta.

La guía de uso está en el README, [§36 Aprobaciones](../README.md#36-aprobaciones). El detalle funcional del motor está en el anexo de este documento:

- **§22** Approval Engine v2 (grupos, quórum, condiciones, auto-aprobación,
  encadenamiento, APIs de flujos y analítica).
- **§22 bis** Motor de políticas común (`app/services/politicas/`, revisión 165):
  las reglas de negocio (bloquear, pedir niveles, avisar, exigir requisitos,
  auto-aprobar) se definen como políticas, no en el motor de aprobaciones; el
  motor de aprobaciones solo ejecuta los pasos que resultan.
- **§22 ter** Gastos sobre el motor de políticas (revisión 166).
- **§22 quater** Ausencias gobernadas por reglas (revisión 167).

## Dónde está

- Servicio: paquete `app/services/approval_engine/` (`_base`, `workflows`,
  `requests`, `pasos`, `diagrama`, `fuentes`, `timeouts`, `analytics`, `groups`,
  `por_correo`, `ausencias`). `from app.services.approval_engine import X` sigue
  valiendo (reexporta los submódulos).
- Modelos: `app/models/billing_reports.py` — tablas `approval_workflows`,
  `approval_steps`, `approval_requests`, `approval_decisions`,
  `approval_request_steps`, `approval_groups`, más
  `FinancialApprovalAuditLog` para los tipos con impacto financiero.
- API: `app/api/v1/endpoints/approvals.py` (`/api/v1/approvals/...`).
- Worker: `process_approval_timeouts`, cada hora (ver `docs/WORKER_TASKS.md`).
- Tests: `tests/test_approvals.py`, `tests/test_auto_approval.py`,
  `tests/test_motor_de_politicas.py`, `tests/test_gastos_sobre_motor_de_politicas.py`.

## Modelo

- **Flujo** (`ApprovalWorkflow`): `entity_type`, `is_active`, `is_default`,
  `trigger_conditions`, `auto_approval_rules`, `chain_on_approval_workflow_id`,
  `sla_block_on_breach`, `diagrama` (diseñador gráfico, se compila a pasos).
  `elegir_flujo` / `find_default_workflow` escogen el flujo de una entidad.
- **Paso** (`ApprovalStep`, y `ApprovalRequestStep` para los pasos que una
  política añade a UNA solicitud): `step_order`; `kind` = `approve` | `inform`;
  `approver_type` (`role`, `user`, `manager`, `any_in_department`, `group`,
  `manager_level` con `approver_level`); `is_optional`; `timeout_hours`
  (72 por defecto) con `on_timeout` = `escalate` | `auto_approve` | `reject`;
  `parallel_quorum` + `required_approvals`; `step_condition`;
  `requires_attachment`; `reminder_hours`. Varios pasos con el mismo
  `step_order` forman una etapa en paralelo.
- **Solicitud** (`ApprovalRequest`): `status` = `pending` | `approved` |
  `rejected` | `cancelled`; `current_step`; `step_started_at`;
  `last_reminder_at`; `final_decision`; `contexto` (JSON para condiciones de
  rama). Puede no tener flujo (`workflow_id` NULL) si solo la abren políticas.
- **Decisión** (`ApprovalDecision`): `decision` = `approved` | `rejected` |
  `delegated` (con `delegate_to`); `step_ref` identifica la rama en etapas
  paralelas; `attachment_url` si el paso lo exige.

## Ciclo de vida

1. **Abrir**: `create_approval_request` (API) o `fuentes.abrir(...)` desde un
   dominio (gastos, ausencias, documentos…), con la evaluación de políticas si
   la hay (`pasos.anadir_por_politicas`). Las reglas de auto-aprobación del
   flujo pueden cerrarla al crearla, salvo niveles pedidos por una política.
2. **Decidir**: `decide_approval_request` (bandeja, `POST /requests/{id}/decide`)
   o enlace firmado del correo (`por_correo`, `GET/POST /email-decision`,
   caducidad `APPROVAL_EMAIL_LINK_HOURS`). Valida autorización del paso,
   segregación de funciones (no aprobar lo propio), voto doble y adjunto.
   Un rechazo cierra la solicitud; una delegación pasa el paso; una aprobación
   avanza cuando la etapa está completa.
3. **Avanzar**: `pasos.avanzar` es el único sitio que avanza una solicitud
   (etapas por `step_order`, ramas paralelas, pasos `inform` que avisan y
   siguen; los pasos opcionales y los que no cumplen su `step_condition` no
   cuentan).
4. **Cerrar**: la decisión final se aplica a la entidad
   (`fuentes.aplicar` / `_apply_entity_final_decision`) y, si hay
   `chain_on_approval_workflow_id`, se abre la solicitud encadenada.
   `cancel_approval_request` la deja en `cancelled`.
5. **Vencimientos**: `process_approval_timeouts` recorre las `pending`; antes
   de vencer envía recordatorio (`reminder_hours`); vencido el paso aplica
   `on_timeout` (escalar a `escalate_to_user_id`, auto-aprobar o rechazar,
   también sobre la entidad) en el contexto de la organización de la solicitud.
6. **Fuera de la oficina**: `GET/PUT /approvals/out-of-office`
   (`ausencias.fijar_ausencia`, campos `users.away_delegate_id`,
   `away_from`, `away_until`): durante el periodo el delegado (misma empresa,
   activo) también recibe y puede decidir las aprobaciones del ausente.

No existe estado `draft`, `expired` ni `archived` en las solicitudes.

## Anexo: motor de aprobaciones y motor de políticas (detalle funcional)

Traído del antiguo `DOCS.md` (§19 a §22 quater), que se retira. Los números de sección (§22, §22 bis…) se conservan para que las referencias sigan valiendo.

### 19. Motor de flujos de aprobación documental
#### Descripción
Los documentos que requieren aprobación (`requires_approval=True`) se gestionan a través del motor multi-nivel (`approval_engine`), el mismo que usan partes de horas, gastos, ausencias, cambios, facturas y presupuestos (ver §22 y el README, «Approval Inbox»). No existe entidad de compras.

#### Cómo funciona
1. Al subir un documento con `requires_approval=True`, el sistema busca el flujo de su categoría (`documents_service._auto_create_approval_request` → `find_document_workflow`).
2. Búsqueda (`_base.find_default_workflow`): primero un flujo activo `entity_type=document` con `trigger_conditions={"category":"<cat>"}`, luego el genérico `entity_type=document` + `is_default=True`. No usa `elegir_flujo` ni el motor de políticas.
3. Si encuentra flujo con pasos, crea un `ApprovalRequest`, lo enlaza en `Document.approval_request_id` y notifica al primer aprobador.
4. «Enviar para aprobación» (`POST /documents/{id}/submit-approval`, acceso `editor`) repite esa búsqueda; sin flujo responde 422. Tras un rechazo o cancelación se puede volver a enviar; con una solicitud activa, 409.
5. Cada decisión avanza el flujo paso a paso. Al completarse, `Document.approval_status` se actualiza automáticamente. Sin solicitud enlazada, `POST /documents/{id}/approve` (acceso `admin` del documento) fija el estado directamente.

#### Configuración por categoría
En Settings → Approval Workflows: crear flujo con `entity_type=document` y `trigger_conditions={"category":"legal"}`. El motor selecciona el flujo más específico automáticamente.

### 20. Gobierno de flujos: separación operación vs configuración
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

### 21. Approval Flows (Config) — capacidades enterprise
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

### 22. Approval Engine v2 Enterprise
#### Tipos de entidad soportados
El diseñador ofrece `document`, `timesheet`, `expense`, `change_request`, `milestone`, `purchase`, `invoice`, `contract`, `budget`, `budget_transfer`, `leave`, `deliverable`, `proposal`, `subcontractor`, `scope_change`, `hire`, `price_change` y `mcp_action` (`entity_type` es texto libre en el API). Abren solicitudes solas y reciben la decisión final: `document`, `mcp_action` y los tipos de `approval_engine/fuentes.py` (`expense`, `timesheet`, `leave`, `change_request`, `invoice`, `budget`, `budget_transfer`); el resto solo se abre a mano o por una automatización y la decisión no se aplica a ninguna entidad (detalle en el README, «Approval Inbox» → *Limitations*).

#### Funcionalidades
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

#### Tabs frontend
- **Grupos**: CRUD de grupos con selección de miembros.
- **Carga**: tabla por aprobador con score, badge de sobrecargado y selector de período.
- **Matriz**: grid entidad × flujo con flujos activos/default por tipo de entidad.

#### APIs principales
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

### 22 bis. Motor de políticas, reglas y flujos (tarea #26, revisión 165)

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

### 22 ter. Gastos sobre el motor de políticas (tarea #27, revisión 166)

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

### 22 quater. Ausencias gobernadas por reglas (tarea #25, revisión 167)

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
