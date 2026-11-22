# Flujo de demanda configurable (22-11-2026)

Motor de flujos de demanda por empresa: un cliente (portal de clientes), un
cliente interno (portal interno) o un operador piden un **cambio en un proyecto**,
una **nueva funcionalidad fuera de todo proyecto** o un **servicio**, y la
solicitud recorre las fases que la empresa haya configurado, con su responsable,
sus decisiones, sus plazos, sus avisos y su trazabilidad inmutable.

**El motor es genérico.** Nada de ningún caso concreto está escrito en el
código: cada empresa define sus tipos de solicitud, sus formularios, sus fases y
sus reglas. El flujo de la empresa piloto (triaje → estudio Digital → CAB →
Legal y Compliance en paralelo → puerta de gobernanza → comité) es **una
plantilla más** de la biblioteca (§2.3), igual que el cambio ITIL, el alta de
proveedor, la compra por importe, la petición de acceso, la iniciativa de
cartera o la petición a RR. HH.

Qué se configura sin código (todo por empresa):

| Pieza | Opciones |
|---|---|
| Tipo de solicitud | nombre (es/en/zh), descripción, **quién puede crearla** (canales: portal de clientes, portal interno de clientes internos, empleado/operador, portal del proveedor), **sobre qué** (alcances: proyecto, servicio del catálogo, activo/CI, nada = iniciativa independiente), flujo, orden, activo |
| Formulario | campos propios con tipo de dato (texto, texto largo, número, importe, fecha, lista, sí/no), quién lo rellena (solicitante o equipo), visible o no para el cliente, **versionado** («original vs refinado», `critical`), obligatorios al enviar (`submit_required`) y por fase (`required_fields`), bloqueados por fase (`locked_fields`), editables por el equipo por fase (`internal_editable`), bloqueo de la ficha para el solicitante desde una fase (`lock_client_from_here`) |
| Fases y pasos | arbitrarios; pasos en **serie** o en **paralelo**; fases **condicionales** (`condition`: datos y/o motor de políticas; si no se cumple, se salta sola y queda en el log); tipo de fase (entrada, trabajo, revisión, aprobación, puerta, comité) |
| Responsables | rol, grupo, persona, departamento, comité (grupo con quórum: uno, todos o mayoría), flujo del **motor de aprobaciones** (bandeja), el propio solicitante y **responsables dinámicos**: PM del proyecto, gestor de la cuenta del cliente, responsable de quien pide, jefe de su departamento, personas de un proveedor |
| Decisiones | aprobar/completar, rechazar, devolver a cualquier fase (`return_targets`), pedir información, posponer (`hold`), saltar con justificación, vía rápida / a comité en las puertas; **destino por decisión** (`targets`, `on_approve`, `on_reject`: siguiente, una fase o un final) |
| Condiciones | umbrales sobre los campos (`gt`, `gte`, `lt`, `lte`, `eq`, `ne`, `in`, `true`, `false`, `empty`, `not_empty`; todas o alguna) y **motor de políticas** (dominio `demanda`) |
| Plazos y escalado | `sla_hours` por fase, aviso al `sla_warn_pct`, vencimiento; **escalado** (`escalation.to`: con el plazo vencido decide también ese responsable) |
| Avisos | por evento (`submitted`, `enter`, `decision`, `info_requested`, `sla_warning`, `sla_breach`, `closed`) y destinatario (solicitante, responsables de la fase, rol, grupo, persona, responsables dinámicos) |
| Al terminar | ejecución manual (a backlog del proyecto, nuevo proyecto, a cartera) y **acciones automáticas** (`on_close_actions`): crear proyecto, petición de cambio, propuesta de cartera, tarea, ticket del service desk, cambio ITSM, Executive Summary PDF/PPTX con **plantilla configurable** (título, campos, fases cuyos dictámenes entran, historial). petición de compra (`create_purchase`: ticket en la cola de compras de ALM, `ALM_PURCHASE_GROUP_ID`, el mismo camino que las compras de licencias y equipos) |
| Versionado | cada cambio de definición sube la versión del flujo; **una solicitud en curso sigue con la versión con la que empezó** (foto en `flow_snapshot`) |
| Plantillas | biblioteca instalable; **exportar/importar** en JSON (`contecflow-demand-flow/v1`) |
| Vista previa | **simulador** (`POST /demand/flows/simulate`: recorrido con unos datos y decisiones forzadas) y **diagrama** para el diseñador visual (`POST /demand/flows/diagram`: nodos y aristas) |

Paquete backend: `app/services/demanda/`. Migración `195_flujo_de_demanda`.
Configuración: **Configuración → Aprobaciones y políticas → Flujos de demanda**
(`/settings/demanda`). Pantalla de trabajo del operador: `/demand`. Portal del
cliente: sección «Solicitudes» (pestaña «Demandas»).

---

## 1. Inventario medido de lo que había (antes de este cambio)

Medido sobre el código el 22-11-2026.

### 1.1 Peticiones de funcionalidad del portal (`feature_requests`)

- Modelo `FeatureRequest` (`app/models/client_portal.py`): `project_id`
  **obligatorio** (`nullable=False`), 7 estados (`new`, `reviewing`,
  `estimated`, `approved`, `rejected`, `in_development`, `done`). El estado
  `approved` significa «**el cliente** aprobó el presupuesto».
- Servicio `app/services/client_portal_service/peticiones.py` (15 funciones) y
  7 endpoints en `app/api/v1/endpoints/client_portal.py`:
  `GET /portal/feature-requests` (cliente), `GET /portal/feature-requests/team`
  (equipo), `POST`, `PATCH`, `POST …/withdraw` (cliente),
  `POST …/respond` (equipo, `require_any_manager`) y `POST …/decide` (cliente).
- `create_feature_request` exige proyecto (`sin_proyecto_para_solicitudes`):
  **el cliente no puede pedir nada fuera de un proyecto**.
- Pantallas del operador que responden (3): `ProjectsPage.tsx` (pestaña
  Solicitudes), `ClientsPageTabs.tsx` (ficha del cliente) y `ClientPortalPage.tsx`.

### 1.2 El fallo («pasa como si se hiciera en el portal»)

1. `POST /portal/feature-requests/{id}/respond` aceptaba `status=approved`
   (`FeatureResponseIn.status`) y `ProjectsPage.tsx` ofrecía la opción
   «Aprobar». Un operador dejaba la solicitud en `approved` — el estado que
   significa «lo aprobó el cliente» — sin que el cliente decidiera nada, y sin
   registro de quién lo hizo (no había `audit_log` en `respond_to_fr`).
2. Al revés, cuando el cliente aprobaba el presupuesto (`/decide`),
   `_apply_client_fr_approval` creaba la petición de cambio (CR) **ya aprobada**
   (`cr.status = approved`): la aprobación del cliente valía como la aprobación
   interna de Control de cambios, aunque a la vez se abría una solicitud en la
   bandeja que se quedaba colgando.
3. Pasar la solicitud a `in_development` (operador) ponía la CR en `approved`
   (`_ESTADO_DE_CR_SEGUN_FR`) sin pasar por su aprobación.
4. La revisión de la CR en Cambios o en la bandeja no volvía a la solicitud.

### 1.3 Piezas reutilizables que ya existían

| Pieza | Dónde | Uso en el flujo de demanda |
|---|---|---|
| Motor de aprobaciones (niveles, grupos, paralelo, escalado, correo, diseñador) | `app/services/approval_engine/` | Un paso puede delegarse en un flujo del motor (`assignee.type = approval_workflow`): se abre una solicitud `demand_step` con `fuentes.abrir` y su decisión final vuelve con `fuentes.aplicar`. Los grupos aprobadores (`ApprovalGroup`) son los comités y equipos de los pasos. La autorización de un paso por rol/grupo/persona/departamento reutiliza `_is_authorized` (incluye delegación por ausencia). |
| Motor de políticas | `app/services/politicas/` | Dominio nuevo `demanda` (coste, esfuerzo, ROI, impacto, transversalidad, tipo…). Una puerta (gate) puede pedir comité si una política publicada devuelve «revisar» o la etiqueta `comite`. |
| Segregación de funciones | `exigir_que_no_sea_suyo`, `grc_sod` | Quien pide no aprueba; quien estudió no vota en el CAB de su estudio (`segregation.not_actor_of_phases`). Las infracciones quedan registradas. |
| Cartera / intake | `cartera_service` (`PortfolioProposal`) | Ejecución «a cartera»: la demanda aprobada sin proyecto entra como propuesta aprobada. |
| Proyectos | `Project`, `plantillas_de_proyecto` | Ejecución «nuevo proyecto». |
| Control de cambios | `change_service` (`ChangeRequest`) | Ejecución «a backlog» de un proyecto existente: CR aprobada por quien decidió de verdad. |
| Documentos | `Document`, `DocumentVersion`, `s3_service.file_storage`, antivirus | Repositorio documental del expediente, etiquetado por fase. |
| PDF / PPTX | `reportlab`, `_pdf_marca`, `python-pptx==1.0.2` (ya en `requirements.txt`) | Executive Summary del comité. |
| Auditoría | `audit_log` + cadena (`cadena_auditoria`) | Cada transición se escribe además en el registro general. |
| Retención y bloqueo legal | `app/db/bloqueo_legal.py` | Tipo nuevo `demand_requests` (expedientes cerrados). |
| Informe de cumplimiento | `informe_de_cumplimiento.py` | 3 controles nuevos (bypass de comité, estancadas, decisiones sin justificación). |

---

## 2. Qué cambia

### 2.1 Arreglo del comportamiento actual (peticiones de funcionalidad)

- `respond` ya **no acepta** `approved`: solo el cliente aprueba su presupuesto
  (`/decide`). El operador estima, rechaza, inicia desarrollo o cierra.
- Cada respuesta del equipo queda en auditoría con su actor
  (`FEATURE_REQUEST_RESPOND`), y la decisión del cliente con el suyo
  (`FEATURE_REQUEST_CLIENT_DECISION`, actor = el usuario del portal).
- La aprobación del cliente crea la CR **enviada** (`submitted`), no aprobada:
  la aprobación interna es otra decisión, con su actor, en Cambios o en la
  bandeja.
- Iniciar desarrollo con la CR pendiente **en la bandeja** devuelve 409
  (`cr_pendiente_de_aprobacion`): se decide allí. Sin flujo en la bandeja,
  iniciar desarrollo revisa la CR como aprobada **por el operador** (queda
  `reviewed_by`/`approved_by` = quien lo hizo, no el cliente).
- Rechazar la CR en Cambios o en la bandeja rechaza la solicitud enlazada,
  con su nota; el `client_approved` del cliente se conserva (son dos decisiones).
- `ProjectsPage.tsx` quita la opción «Aprobar» del operador.

### 2.2 El motor de flujos de demanda

Conceptos (todo por empresa, `organization_id`):

- **Tipo de solicitud** (`demand_request_types`): `project_change` (cambio en
  un proyecto: exige proyecto), `new_feature` (nueva funcionalidad: proyecto
  existente **o iniciativa independiente**), `service`, o los que cree la
  empresa. Dice en qué canales se ofrece (portal de clientes, portal interno,
  operador) y qué flujo sigue.
- **Flujo** (`demand_flows`): definición JSON versionada (cada cambio sube
  `version`). Cada expediente guarda la **foto** del flujo con el que nació
  (`flow_snapshot`): cambiar el flujo no altera expedientes en curso.
- **Expediente** (`demand_requests`): un expediente único vivo por solicitud.

#### Definición del flujo (JSON, validada por `demanda.definicion.validar`)

```jsonc
{
  "fields": [            // campos del expediente (además de título y proyecto)
    {"key": "descripcion_funcional", "label": {"es": "…", "en": "…", "zh": "…"},
     "type": "textarea",  // text | textarea | number | money | date | select | boolean
     "options": [],       // con select: [{"value": "alto", "label": {…}}]
     "critical": true,    // versionado (original del cliente vs refinado)
     "owner": "client",   // client | internal: quién lo rellena normalmente
     "client_visible": true,
     "policy_field": "coste"   // opcional: lo expone al motor de políticas
    }
  ],
  "submit_required": ["descripcion_funcional", "justificacion"],  // mínimo exigible al enviar
  "phases": [
    {
      "key": "estudio", "name": {"es": "Estudio", …},
      "kind": "intake | work | review | approval | gate | committee",
      "parallel": false,                      // pasos en serie (false) o en paralelo (true)
      "steps": [
        {"key": "estudio_digital", "name": {…},
         "mode": "task | approval",           // task: completar; approval: aprobar/rechazar
         "assignee": {"type": "role | group | user | department | committee | approval_workflow | requester",
                      "value": "pm | <group_id> | <user_id> | <dept> | <workflow_id>",
                      "label": "Equipo Digital"},
         "quorum": "any | all | majority",     // con group/committee: votos necesarios
         "optional": false}
      ],
      "decisions": ["approve", "reject", "return", "request_info", "skip", "hold"],
      "on_approve": "next | <phase_key> | end:approved",
      "on_reject": "end:rejected | <phase_key>",
      "return_targets": ["estudio"],          // a qué fases se puede devolver
      "required_fields": ["solucion_tecnica", "coste"],  // para aprobar/completar la fase
      "client_editable": true,                // el cliente puede editar la ficha en esta fase
      "internal_editable": ["solucion_tecnica", "coste"], // campos que edita el equipo aquí (vacío = todos los internal)
      "lock_client_from_here": false,         // desde esta fase la ficha queda bloqueada para el cliente
      "sla_hours": 72, "sla_warn_pct": 80,
      "pause_on_info": true,                  // «pendiente de información» no cuenta en métricas
      "segregation": {"not_requester": true, "not_actor_of_phases": ["estudio"]},
      "documents_tag": "cab_security_report", // etiqueta por defecto de lo que se adjunta aquí
      "notify": [{"event": "enter | decision | sla_warning | sla_breach | info_requested | closed",
                  "to": {"type": "requester | assignees | role | group | user", "value": "…"}}],
      "gate": {                                // solo kind = gate
        "conditions": [{"field": "coste", "op": "gt", "value": 50000}],
        "match": "any",
        "use_policies": true,                  // política «demanda» con decisión review o etiqueta comite
        "if_true": "comite", "if_false": "end:approved",
        "allow_bypass": true                   // vía rápida aunque se cumplan: justificación obligatoria
      },
      "committee": {"executive_summary": true} // solo kind = committee: genera PDF y PPTX al agendar
    }
  ],
  "execution": ["backlog", "new_project", "portfolio"],  // qué se hace al aprobar al final
  "notify": [ … ]                                         // avisos del flujo entero (mismo formato)
}
```

Decisiones (`POST …/decide`):

| Decisión | Efecto | Justificación |
|---|---|---|
| `approve` / `complete` | El paso queda aprobado/completado; si la fase está completa (todos sus pasos, o el quórum), se va a `on_approve` | opcional |
| `reject` | Va a `on_reject` (fin rechazado o fase de reformulación) | **obligatoria** |
| `return` | Vuelve a la fase indicada (de `return_targets`) | **obligatoria** |
| `request_info` | Estado `pending_info`: vuelve al cliente; **el reloj del SLA se para** | **obligatoria** |
| `skip` | Salta la fase | **obligatoria** |
| `fast_track` / `to_committee` | Puerta de gobernanza: vía rápida o comité. Vía rápida con umbrales superados = **bypass** | **obligatoria** en bypass |
| `hold` | En espera (pospuesta) | **obligatoria** |

Reglas comunes:

- **Segregación**: quien pide no decide ningún paso (`not_requester`, por
  defecto); `not_actor_of_phases` impide decidir a quien decidió en esas fases
  (quien estudió no vota en el CAB). Las infracciones se registran en GRC.
- **Paralelo**: con `parallel: true` todos los pasos se abren a la vez y la
  fase se aprueba cuando todos aprueban (Legal y Compliance); un rechazo
  rechaza la fase.
- **Bloqueo de la ficha**: desde la primera fase con `lock_client_from_here`
  (el CAB en la plantilla), el cliente solo añade comentarios y **anexos
  registrados** (`is_annex = true`).
- **Versionado**: cada cambio de un campo `critical` deja una fila en
  `demand_field_versions` con su origen (`client` o `internal`), fase, autor y
  fecha. El valor original del cliente nunca se pierde.
- **Log inmutable**: `demand_transitions` (usuario o cliente, rol, fecha,
  decisión, justificación) con hash encadenado; la base rechaza `UPDATE` y
  `DELETE` (eventos `before_update`/`before_delete` del ORM).
- **SLA**: `sla_due_at` por fase; el trabajo diario `demanda_plazos` avisa al
  `sla_warn_pct` y al vencer, una sola vez por fase y ronda.
- **Avisos**: notificación interna (`Notification`) y WebSocket; al cliente
  por WebSocket del portal.

### 2.3 Biblioteca de plantillas

`app/services/demanda/biblioteca.py` (instalar: `POST /demand/templates/{clave}/install`;
el resultado es un flujo normal, editable, más sus tipos de solicitud si no existían):

| Clave | Plantilla | Lo que muestra |
|---|---|---|
| `piloto_digital` | Nueva funcionalidad con CAB y comité | la de la empresa piloto (abajo) |
| `cambio_itil` | Petición de cambio ITIL | fases condicionales por tipo de cambio: estándar sin CAB, normal con CAB, urgente con CAB de emergencia (4 h y escalado); al aprobar crea el cambio ITSM |
| `alta_proveedor` | Alta de proveedor | compras; protección de datos solo si trata datos personales; dirección solo si el importe anual > 50.000 o lo pide una política; al aprobar crea una tarea |
| `compra_por_importe` | Petición de compra | responsable de quien pide; finanzas si > 3.000; dirección si > 20.000 o política; al aprobar abre la petición de compra en la cola de compras de ALM |
| `acceso_permisos` | Petición de acceso o permisos | responsable de quien pide; seguridad solo para nivel administración (segregación: no el mismo que el responsable); al aprobar abre un ticket |
| `iniciativa_cartera` | Iniciativa de cartera con business case | PMO y comité de cartera con Executive Summary; al aprobar crea la propuesta en Cartera |
| `peticion_rrhh` | Petición a RR. HH. | una fase atendida por RR. HH. |

La empresa demo trae instalada la piloto (migración 195 y `seed_demanda`). Las
demás usan roles y responsables dinámicos, así que funcionan sin crear grupos.

#### Plantilla piloto (`piloto_digital`)

`app/services/demanda/plantillas.py` → `sembrar_plantilla_piloto(db, org_id)`:

1. **Solicitud** (`intake`, cliente): ficha inicial — descripción funcional,
   justificación, retorno esperado (ROI o beneficio), adjuntos (mockups,
   normativa, presentaciones). Triaje por el *Service Delivery Manager / Product
   Owner* de Digital (grupo «Triaje Digital»): aprobar o **pedir información**
   («Pendiente de información», sin contar en métricas).
2. **Estudio** (`work`, equipo Digital): viabilidad técnica, arquitectura,
   impacto en legados, ciberseguridad; business case refinado — solución,
   esfuerzo (horas/equipo), coste, cronograma, retorno ajustado.
3. **CAB de Digital** (`review`, comité «CAB Digital», mayoría): revisión de
   pares. Aprobado → Normativa; Rechazado / A reformular → vuelve a Estudio.
   Desde aquí la ficha queda bloqueada para el cliente. Quien estudió no vota.
4. **Normativa** (`approval`, **paralelo**): Legal y Compliance; ambos deben aprobar.
5. **Gobernanza** (`gate`): Digital decide si va a Comité de Digitalización
   (umbrales: coste > 50.000, esfuerzo > 800 h, impacto estratégico alto,
   transversal; y políticas del dominio `demanda`). Vía rápida → aprobada.
6. **Comité de Digitalización** (`committee`): se agenda; al agendar se genera
   el Executive Summary (PDF y PPTX) con los datos refinados y los dictámenes
   de CAB, Legal y Compliance. Resolución: aprobada (a backlog o nuevo
   proyecto) o rechazada / pospuesta (en espera).

Grupos que crea (si no existen): «Triaje Digital», «Equipo Digital», «CAB
Digital», «Legal», «Compliance», «Comité de Digitalización» (`ApprovalGroup`,
sin miembros: la empresa los rellena).

---

## 3. Modelo de datos (migración 195)

| Tabla | Para qué |
|---|---|
| `demand_request_types` | Tipos de solicitud por empresa (clave, nombres, canales, si exige proyecto, flujo) |
| `demand_flows` | Flujos (definición JSON, versión, activo) |
| `demand_requests` | El expediente (estado, fase actual, ronda, datos, foto del flujo, SLA, pausa, resultado) |
| `demand_step_states` | Estado de cada paso por fase y ronda (votos, decisor, solicitud del motor de aprobaciones) |
| `demand_transitions` | **Log inmutable** de transiciones (hash encadenado) |
| `demand_field_versions` | Versiones de los campos críticos (append-only) |
| `demand_documents` | Repositorio documental del expediente, etiquetado por fase |
| `demand_comments` | Comentarios (internos o visibles para el cliente) |

Datos personales: los adjuntos pueden llevarlos (`personal_data` lo marca quien
sube); el acceso a cada descarga queda en auditoría y en `document_access_logs`.
Retención: tipo `demand_requests` en Configuración → Retención (solo
expedientes cerrados, desde el cierre); respeta el bloqueo legal (por `id`,
`client_id`, `project_id`, `requester_user_id`).

## 4. API

Operador (`/api/v1/demand`, capacidades `demanda.ver` (internos), `demanda.gestionar`
(admin y PM) y `demanda.config` (admin)):

```
GET    /demand/catalog                         opciones del configurador (+ templates)
GET    /demand/types            POST /demand/types       PATCH /demand/types/{id}
GET    /demand/flows            POST /demand/flows       GET|PATCH /demand/flows/{id}
POST   /demand/flows/validate   {definition}  -> {errors: [{path, code}]}
POST   /demand/flows/simulate   {definition, data, decisions} -> {errors, path, end, warnings}
POST   /demand/flows/diagram    {definition}  -> {nodes, edges}
GET    /demand/flows/{id}/export               JSON contecflow-demand-flow/v1
POST   /demand/flows/import                    importa como flujo nuevo
GET    /demand/templates                       biblioteca
POST   /demand/templates/{clave}/install       instala (idempotente)
POST   /demand/flows/pilot-template            atajo: instala piloto_digital
GET    /demand/requests?status=&phase=&type=&pending_for_me=&q=
POST   /demand/requests                        {type_key, title, project_id?, scope_kind?, scope_ref_id?,
                                                client_id?, requester_user_id? (gestionar), data, submit}
GET    /demand/requests/{id}                   expediente completo
PATCH  /demand/requests/{id}/fields            {title?, data, note?}
POST   /demand/requests/{id}/submit            {note?}
POST   /demand/requests/{id}/decide            {step_key, decision, target_phase?, justification?}
POST   /demand/requests/{id}/withdraw          {reason?}
POST   /demand/requests/{id}/comments          {body, internal}
POST   /demand/requests/{id}/documents         multipart: file, tag, personal_data, internal
GET    /demand/requests/{id}/documents/{doc_id}/download
POST   /demand/requests/{id}/committee         {date}  agenda y genera el Executive Summary
POST   /demand/requests/{id}/executive-summary regenera PDF y PPTX
POST   /demand/requests/{id}/execute           {mode: backlog|new_project|portfolio, name?, pm_id?}
GET    /demand/requests/{id}/verify            {ok}: cadena del log íntegra
GET    /demand/metrics
GET    /demand/mine/types?channel=             tipos de mi canal (cualquier usuario con sesión;
GET    /demand/mine     POST /demand/mine        un externo usa siempre supplier_portal)
```

Portal de clientes (`/api/v1/portal/demand`, token del cliente, `can_request_changes`):

```
GET    /portal/demand/types                    {types (canal client_portal), projects}
GET    /portal/demand/requests
POST   /portal/demand/requests                 {type_key, title, project_id?, scope_kind?, data, submit}
GET    /portal/demand/requests/{id}            vista del cliente (sin lo interno; info_request)
PATCH  /portal/demand/requests/{id}            {title?, data} solo en fases editables por el cliente
POST   /portal/demand/requests/{id}/submit     enviar o devolver la información pedida
POST   /portal/demand/requests/{id}/decide     pasos cuyo responsable es el solicitante
POST   /portal/demand/requests/{id}/comments   {body}
POST   /portal/demand/requests/{id}/documents  multipart: file, tag (anexo registrado si está bloqueada)
GET    /portal/demand/requests/{id}/documents/{doc_id}/download
POST   /portal/demand/requests/{id}/withdraw   {reason}
```

Punto de entrada común para canales (`app/services/demanda/entrada.py`). Contrato
que usa el portal interno de clientes internos (`app/services/clientes_internos/peticiones.py`):

```python
s = entrada.Solicitante(kind="internal_user" | "employee" | "supplier" | "client_user",
                        user=<User o ClientUser>, client_id=<cliente o unidad>)
entrada.crear(db, s, {"title", "description"?, "kind"?, "type_key"?, "project_id"?,
                      "estimated_budget"?, "data"?, "submit"?}) -> dict (resumen)
entrada.listar(db, s) -> list[dict]
```

Sin `type_key`, el tipo es el primero (por orden) de los ofrecidos en el canal
(`tipo_por_defecto`; `kind="servicio"` prefiere un tipo con alcance servicio):
se cambia ordenando los tipos en Configuración. `description` y
`estimated_budget` van al primer campo de texto largo y al campo de coste del
flujo. Si faltan obligatorios, queda en borrador.

### Formas de respuesta

`RequestSummary`: `id, code, title, type_key, type_name, origin, status,
current_phase_key, current_phase_name, project_id, project_name, standalone,
requester_name, created_at, submitted_at, sla_due_at, sla_state
(ok|warning|breached|paused|null), closed_at`.

`RequestDetail` = `RequestSummary` + `flow {id, name, version}`, `data`,
`fields [{key, label, type, options, critical, owner, editable, required_now}]`,
`phases [{key, name, kind, status (done|current|pending|skipped), entered_at,
sla_due_at, steps [{key, name, mode, assignee_label, status, decided_by_name,
decided_at, note, votes, can_decide, decisions}]}]`, `transitions [{id,
from_phase, to_phase, step_key, decision, actor_name, actor_kind
(user|client|system), actor_role, justification, created_at}]`,
`field_versions [{field, value, source (client|requester|internal), phase_key, author_name, created_at}]`,
`documents [{id, tag, phase_key, file_name, size, mime, uploaded_by_name,
is_annex, personal_data, created_at}]`, `comments [{id, body, internal,
phase_key, author_name, author_kind, created_at}]`, `committee {required,
date, reasons}`, `result {kind, project_id, change_request_id, proposal_id}`,
`actions {can_edit_fields, can_submit, can_comment, can_upload, can_withdraw,
can_schedule_committee, can_generate_summary, can_execute}`, `client_locked`,
`metrics {effective_hours, paused_hours}`.

Los nombres de tipos, fases, pasos y campos llegan resueltos al idioma de quien
pide (`Accept-Language`), con `*_i18n` aparte.

Estados del expediente: `draft`, `in_progress`, `pending_info`, `on_hold`,
`approved`, `rejected`, `withdrawn`, `done`.

## 5. GRC

- **Auditoría inmutable**: `demand_transitions` (hash encadenado, sin UPDATE ni
  DELETE) + `audit_log` de cada acción (crear, editar campo, decidir, adjuntar,
  descargar, generar resumen, ejecutar).
- **Segregación**: ver 2.2; infracciones en `sod_violations` vía `grc_sod`.
- **RGPD de adjuntos**: marca `personal_data`, antivirus al subir, descarga
  auditada, retención por tipo y bloqueo legal.
- **Informe de cumplimiento** (`informe_de_cumplimiento.generar`):
  `demand_committee_bypass` (vías rápidas con umbrales superados en 90 días),
  `demand_stalled` (expedientes con el SLA vencido), `demand_decisions_without_justification`
  (rechazos, devoluciones, saltos o bypass sin justificación: debería ser 0),
  `demand_log_integrity` (hash encadenado del log de cada expediente).
- **Trabajo** `app.worker.demanda_plazos` (cada hora, por organización): avisos de
  plazo y vencimientos (`revisar_plazos`).

## 6. Ficheros

- Backend: `app/models/demanda.py`, `app/services/demanda/` (`__init__`,
  `definicion` (validar, simular, diagrama), `config`, `biblioteca`, `plantillas`,
  `acceso`, `motor`, `expediente`, `documentos`, `avisos`, `resumen_ejecutivo`,
  `ejecucion`, `consultas`, `serializacion`, `cumplimiento`, `trabajos`, `entrada`),
  `app/services/politicas/dominios/demanda.py`, `app/api/v1/endpoints/demanda.py`,
  `app/api/v1/endpoints/portal_demanda.py`, `alembic/versions/195_flujo_de_demanda.py`,
  `app/db/seed_parts/demanda.py`. Tocados: `approval_engine/fuentes.py` (tipo
  `demand_step`), `politicas/catalogo.py`, `db/bloqueo_legal.py` (retención),
  `informe_de_cumplimiento.py`, `core/capacidades.py`, `worker.py`,
  `client_portal_service/peticiones.py`, `change_service.py`,
  `endpoints/client_portal.py`, `api/v1/routers/core.py`, `db/seed.py`,
  `scripts/codemods/errores_con_codigo/demanda.json` (38 códigos, sincronizados).
- Frontend: `frontend/src/pages/DemandaPage.tsx`, `frontend/src/components/demanda/*`,
  `frontend/src/pages/portal-client/PortalDemandas.tsx`, `services/api/demanda.ts`,
  sección `demanda` en `pages/settings/catalogoDeAjustes.tsx`.
  Portal del proveedor: pestaña «Mis solicitudes» (`pages/proveedores/PestanaSolicitudes.tsx`,
  pide por `/demand/mine`, canal `supplier_portal`). Selector de alcance servicio/activo con datos
  reales (`GET /demand/mine/scope-options?kind=service|asset`; en el portal, `/portal/demand/scope-options`).
  `/demand` está abierta a cualquier sesión («Mis solicitudes»); «Todas» y las métricas piden `demanda.ver`.
- Tests: `tests/test_flujo_de_demanda.py`, `tests/test_portal_fr_actores.py`,
  `frontend/src/__tests__/demanda.test.ts` (escritos, no ejecutados).

## 7. Migración 195

Probada el 22-11-2026 sobre una copia de `clarive.db` (en versión 194): upgrade →
8 tablas y la plantilla piloto en la demo (1 flujo, 3 tipos); downgrade → sin
tablas; upgrade de nuevo → igual. Idempotente (crea solo lo que falta).

## 8. Pendiente conocido

- El diseñador visual pinta el diagrama de `/demand/flows/diagram`; no reutiliza el
  diseñador del motor de aprobaciones (su modelo son pasos de aprobación, no fases con
  ramas de devolución y puertas).
