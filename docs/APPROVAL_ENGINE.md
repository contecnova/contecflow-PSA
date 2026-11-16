# Motor de aprobaciones

Referencia breve del motor de aprobaciones tal como está en el código (revisado
el 2026-11-16). La versión anterior de este documento (mayo 2026) describía una
máquina de estados `DRAFT/PENDING/EXPIRED/ARCHIVED`, modelos `ApprovalVote` y
tipos `sequential/quorum/any` que **no existen**; queda sustituida por esta.

La documentación funcional completa está en `DOCS.md`:

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
