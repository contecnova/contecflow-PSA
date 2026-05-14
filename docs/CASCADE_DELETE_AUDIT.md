# Cascade DELETE Audit — Cross-tenant safety (#58)

> Auditoría de seguridad multi-tenant sobre las relaciones SQLAlchemy con
> `cascade="all, delete-orphan"` y FKs con `ondelete="CASCADE"` para
> garantizar que un DELETE NO pueda atravesar fronteras de organización.

**Fecha**: 2026-05-14
**Audit**: #58 (relacionado con #7 multi-tenancy, #56-57 N+1)
**Migración base**: `076_multitenancy_org_id_columns` — añade `organization_id`
nullable + FK + index a 301 tablas de negocio.

## TL;DR

- **101 relationships** con `cascade="all, delete-orphan"` en `app/models/`.
- **393 FKs** con `ondelete="CASCADE"` o `ondelete="SET NULL"` (incluye PKs no-cascade).
- **Conclusión**: tras la migración 076, cada hijo en una cascade DELETE comparte
  `organization_id` con su padre (todas las tablas tienen la columna), por lo que
  cascade no puede cruzar tenants **si las inserciones se hacen correctamente**.
  El riesgo real residual está en las **inserciones**, no en los DELETE en sí.
- **No se encontraron casos CLAROS de cross-tenant cascade dangerous** que justifiquen
  un fix inmediato. Las cascades existentes están alineadas con la jerarquía
  natural de tenant.
- Recomendaciones de **defensa en profundidad** abajo (no críticas).

---

## 1. Inventario de cascades en TOP-5 modelos

### 1.1 `Project` (app/models/project.py)

| Relación | Hijo | Cascade | Cross-tenant posible? |
|---|---|---|---|
| `phases` | `ProjectPhase` | `all, delete-orphan` + FK `ondelete="CASCADE"` | **NO** — `ProjectPhase.project_id` FK → `projects.id`. Ambos tienen `organization_id`. La cascade solo borra fases del proyecto en cuestión. |
| `members` | `ProjectMember` | `all, delete-orphan` + FK `ondelete="CASCADE"` | **NO** — mismo patrón. `ProjectMember` tiene `organization_id`. |
| `tasks` | `Task` | **sin cascade explícito** (no se borran al borrar Project) | N/A — actualmente `Task.project_id` SÍ tiene `ondelete="CASCADE"` a nivel DB, pero la relación ORM no propaga delete-orphan. La DB hará la cascada. |
| `imputations` | `Imputation` | **sin cascade ORM**, pero FK `ondelete="CASCADE"` | DB-level cascade. `Imputation.organization_id` también existe. |

**FK descendentes a `projects.id` con `ondelete="CASCADE"` (deletes en DB):**
- `project_phases`, `project_members`, `tasks`, `imputations`, `sprints`,
  `epics`, `wiki_pages` (epics.py), `financial.*`, `cmdb` partials, `activity`,
  `bookings`, `cab` partials, `git_integration`, etc.

Todos tienen `organization_id` propio (audit #7) y se alimentan a partir del
proyecto padre, por lo que el invariante **child.organization_id ==
parent.organization_id** se mantiene si las inserciones lo respetan.

### 1.2 `Client` (app/models/clients.py)

| Relación | Hijo | Cascade | Cross-tenant posible? |
|---|---|---|---|
| `contacts` | `ClientContact` | `all, delete-orphan` + FK `ondelete="CASCADE"` | **NO** — comparten org. |
| `portal_config` | `ClientPortalConfig` | `all, delete-orphan` + FK `ondelete="CASCADE"` | **NO**. |
| `license_links` | `ClientLicenseLink` | `all, delete-orphan` + FK `ondelete="CASCADE"` | **NO** — pero ojo: `ClientLicenseLink` también referencia `alm_licenses.id` con `ondelete="CASCADE"`. Borrar un link no propaga al ALMLicense. OK. |
| `contract_links` | `ClientContractLink` | `all, delete-orphan` + FK `ondelete="CASCADE"` | **NO** — análogo a license_links. |
| `projects` | `Project` | **sin cascade** — `Project.client_id` es `ondelete="SET NULL"` | Borrar un cliente NO borra sus proyectos. Solo desvincula. Decisión consciente. |

### 1.3 `Organization` (app/models/mfa.py)

| Relación | Hijo | Cascade | Cross-tenant posible? |
|---|---|---|---|
| `users` | `User` | **sin cascade ORM** | `User.organization_id` FK es `ondelete="CASCADE"` (mfa.py user.py L32) — borrar la Organization borra todos sus usuarios. **Por diseño**: es el root tenant. |
| `user_memberships` | `UserOrganizationMembership` | `all, delete-orphan` | **NO** — propio del tenant. |
| `member_users` | secondary (viewonly) | n/a | viewonly, no propaga. |

**Análisis crítico**: el modelo `Organization` SÍ es el root tenant. Borrarla
borra usuarios (cascade), y de ahí en adelante muchas FKs `users.id` con
`ondelete="SET NULL"` desvinculan. Las FKs `organizations.id ondelete="CASCADE"`
en otras tablas (cab, white_label, portal_conversations, bi_collaboration,
activity, workflow_designer, service_desk_ai_governance, revenue) DELETE-cascadean
todo el tenant. **Esto es el comportamiento esperado** para purgar un tenant.

- **Inconsistencia detectada**: hay un mix entre `ondelete="CASCADE"` (mayoría
  tablas nuevas — cab, revenue, white_label) y FKs sin `ondelete` (`ForeignKey("organizations.id")`)
  en la mayoría de las tablas migradas en #076 (clients, projects, tasks, etc.).
  Esto significa que borrar una Organization fallará por FK constraint en muchas
  tablas (RESTRICT por defecto en MySQL/Postgres), bloqueando la purga total.
  **NO es un agujero de seguridad**, sino una decisión a tomar: ¿permitir purga
  cascada completa o requerir hard-delete manual? Ver Recomendación R1.

### 1.4 `Task` (app/models/task.py)

| Relación | Hijo | Cascade | Cross-tenant posible? |
|---|---|---|---|
| `comments` | `TaskComment` | `all, delete-orphan` + FK `ondelete="CASCADE"` | **NO** — `TaskComment.organization_id` existe. |
| `subtasks` | `Task` (self-ref) | sin cascade (FK `ondelete="SET NULL"` en `parent_task_id`) | Subtasks quedan huérfanas, no se borran. OK. |
| `imputations` | `Imputation` | sin cascade ORM, FK `ondelete="SET NULL"` en `imputations.task_id` | Las imputaciones se desvinculan, no se borran. OK. |

### 1.5 `Sprint` (app/models/sprints.py)

| Relación | Hijo | Cascade | Cross-tenant posible? |
|---|---|---|---|
| `sprint_tasks` | `SprintTask` | `all, delete-orphan` + FK `ondelete="CASCADE"` | **NO** — `SprintTask` tiene `organization_id`. |

Adicionalmente `SprintTask.task_id` también es `ondelete="CASCADE"` a `tasks.id`,
pero la dirección es task → sprint_task, no al revés. Sprint → SprintTask es
correcto y seguro.

---

## 2. Otros modelos con cascade revisados (sample)

| Modelo padre | Hijos cascadeados | Cross-tenant risk |
|---|---|---|
| `MFAConfig` | `MFABackupCode` | NO |
| `Document` | `DocumentVersion`, `DocumentPermission`, `DocumentTag` | NO |
| `Ticket` (service_desk) | `TicketComment`, `TicketAttachment`, `KnownErrorTicket` | NO |
| `Problem` | `KnownError`, `IncidentToProblem` | NO |
| `WikiSpace` | `WikiPage` → `WikiVersion`, `WikiComment` | NO |
| `Epic` | `EpicTask`, `EpicDependency` | NO |
| `AIConversation` | `AIMessage`, `AIAgentStep` | NO |
| `PortalConversation` | `Participants`, `Messages`, `Audits` | NO |
| `ProjectTemplate` (advanced_config) | `TemplatePhase` → `TemplateTask`, `TemplateRisk`, `TemplateDeliverable` | NO |
| `ALMContract` | `ALMLicense` → `ALMLicenseAssignment`, `ALMSoftwareInstall` | NO |
| `ALMAsset` | `ALMSoftwareInstall`, `AssetHistory` | NO |
| `CABMeeting` (cab.py) | members, votes | NO |
| `KeyResult` (okrs.py) | progress updates | NO |
| `CIItem` (cmdb.py) | relations, history | NO |
| `PublicForm` | submissions | NO |
| `Booking` | participants | NO |
| `BillingReport` | runs, definitions | NO |
| `OnCallSchedule` | entries | NO |

En todos los casos analizados, padre e hijos comparten ámbito tenant (mismo
`organization_id`).

---

## 3. Hallazgos

### 3.1 Sin riesgo crítico de cross-tenant en cascade DELETE

Post-migración #076, todas las tablas hijas tienen `organization_id`. La
combinación padre → hijo siempre es de la misma org siempre que las
inserciones respeten el invariante. **No se encontró ningún caso de cascade
que pueda atravesar tenants** porque ningún cascade conecta entidades cuyo
`organization_id` pudiera diferir por construcción.

### 3.2 Riesgo lateral: FKs sin `ondelete` apuntando a `organizations.id`

Las tablas migradas en #076 declaran `ForeignKey("organizations.id")` sin
especificar `ondelete`. El comportamiento DB por defecto es RESTRICT — bloqueará
el DELETE de una Organization. Otras tablas SÍ ponen `ondelete="CASCADE"`. Mix
incoherente:

**Sin ondelete (RESTRICT por defecto, ~290 tablas — desde #076):**
clients, projects, tasks, imputations, expenses, financial.*, sprints,
project_phases, project_members, client_contacts, etc.

**Con ondelete="CASCADE" (~25 tablas):**
cab.*, white_label, portal_conversations, bi_collaboration, activity (parcial),
workflow_designer, service_desk_ai_governance, revenue (todas), user (PRIMARIO).

**Implicación**: borrar una Organization en producción HOY fallaría con
IntegrityError por las primeras (RESTRICT). Esto es PROTECTOR contra purga
accidental, pero IMPIDE una funcionalidad de "delete tenant" si se necesita.

### 3.3 `User.organization_id ondelete="CASCADE"`

`User.organization_id` tiene `ondelete="CASCADE"` (user.py:32). Borrar una
Organization borra todos sus usuarios. De ahí, muchos campos `*_id → users.id`
están con `ondelete="SET NULL"` (assignees, creators, reporters, account_managers),
así que se desvinculan limpiamente. **OK por diseño** — un user no debe sobrevivir
a su tenant.

### 3.4 `UserOrganizationMembership` con `RESTRICT`

`UserOrganizationMembership.organization_id` declara `ondelete="RESTRICT"` (user.py:89).
Esto **bloqueará** la cascade de Organization → users (#3.3), creando un deadlock
potencial al intentar borrar una Organization que tenga memberships. La cascade
`all, delete-orphan` del lado ORM (mfa.py:59) borraría primero los memberships,
pero solo si la sesión carga la relación antes del DELETE. **Recomendación R3**.

---

## 4. Recomendaciones

### R1 — Decidir política de "delete tenant"
Definir si una Organization se puede borrar a nivel DB. Opciones:
- **(A) Bloquear (status quo de facto)**: mantener mix actual; deletes
  manuales/scripted con orden explícito. Ventaja: imposible borrar tenant
  por accidente. Desventaja: no hay "soft tenant purge" automática.
- **(B) Permitir cascade full**: añadir `ondelete="CASCADE"` a TODAS las FKs
  hacia `organizations.id` en una migración nueva. Requiere tests exhaustivos.
- **(C) Soft delete tenant**: añadir `is_active=False` en Organization y filtrar
  globalmente. Mantener FKs como están.

**No se aplica fix en este audit** — decisión de producto.

### R2 — Guardia en servicios DELETE para padres con cascade
En endpoints `DELETE /projects/{id}`, `DELETE /clients/{id}`, etc., además
del `enforce_abac(..., action="delete")` (audit ABAC), **verificar
explícitamente** que `entity.organization_id == current_user.organization_id`
antes del `db.delete(entity)`. Esto es defensa-en-profundidad ante un bug
hipotético de inserción que metiera un hijo en otra org. (Probablemente ya se
hace por filtros de listing, pero documentar la garantía).

### R3 — Resolver el deadlock `UserOrganizationMembership` ondelete RESTRICT
Si la política es permitir cascade tenant (R1-B), cambiar
`UserOrganizationMembership.organization_id` a `ondelete="CASCADE"`. Si no,
documentarlo como blocker intencional.

### R4 — Tests de invariante cross-tenant
Añadir un test que para cada cascade ORM, intente borrar un padre con un hijo
que tenga `organization_id` DISTINTO (inserción manual sin pasar por servicio).
El test debe FALLAR o detectar el cross-tenant. Esto detectaría bugs futuros
de inserción.

### R5 — No-action (status quo OK)
Los cascades existentes son razonables y NO se han modificado en este audit.
Cualquier cambio requiere migración + tests específicos del dominio que están
fuera del scope de #58.

---

## 5. Conteo final

```
$ grep -rn 'cascade="all, delete-orphan"' app/models/ | wc -l
101

$ grep -rn 'ondelete="CASCADE"' app/models/ | wc -l
393

$ grep -rn 'cascade=' app/models/ | wc -l
101    # (las únicas variantes encontradas son all,delete-orphan)
```

**Modificaciones de código: 0** (solo documentación, según scope del audit).
