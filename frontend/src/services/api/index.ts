// Audit #C10 — barrel for the `services/api/` domain split.
//
// `services/api.ts` is a 1,890-LOC god-file that aggregates ~40 domain APIs and
// is imported by ~200 components. Splitting it in one go would force a rewrite
// of every import. Instead we adopt a progressive structure:
//
//   • `_core.ts`     — unchanged copy of the original god-file. New code should
//                      NOT add to it; it stays as-is so we don't move every
//                      target at once.
//   • `<domain>.ts`  — newly extracted, strictly-typed slices (auth, users,
//                      projects, tasks, settings, …). The barrel re-exports
//                      them AFTER `_core.ts` so the typed version wins via the
//                      explicit named re-export shadowing the `export *`.
//   • `index.ts`     — this file: the public surface. Both
//                      `from '.../services/api'` (folder) and
//                      `from '.../services/api/_core'` (file) keep working.
//
// To migrate a slice: extract it from `_core.ts` into `services/api/<slice>.ts`,
// add a named re-export below, and (optionally) delete the original block from
// `_core.ts` once nothing imports it directly.

export * from './_core'
export { default } from './_core'

// ── Typed slices (override the matching name from `_core.ts`) ─────────────────
//
// TypeScript resolves a named re-export with priority over a `export *` wildcard
// for the same identifier, so consumers automatically get the typed surface.
export { authApi } from './auth'
export type {
  LoginCredentials,
  LoginResponse,
  MeResponse,
  ForgotPasswordPayload,
  ResetPasswordPayload,
  ChangePasswordPayload,
} from './auth'

export { conectoresApi, mensajeDeConector } from './conectores'
export { aiGovernanceApi } from './aiGovernance'
export { API_BASE_URL, apiUrl, apiUrlAbsoluta, apiWsUrl, wsBase } from './urls'
export { leccionesApi } from './lecciones'
export { gastosApi } from './gastos'
export { presupuestosApi } from './presupuestos'
export type { Presupuesto, FichaPresupuesto, Partida, Informe as InformeDePresupuesto, Ambito as AmbitoDePresupuesto, Plantilla as PlantillaDePresupuesto, Campana as CampanaDePresupuesto, Area as AreaDeEmpresa, Comparacion as ComparacionDePresupuestos, Recurrencia, MetodoPrevision, Pedido as PedidoDePresupuesto, Traspaso as TraspasoDePresupuesto, RenglonDelCuadro } from './presupuestos'
export type { Justificante, Parte as ParteDeGasto, Politica as PoliticaDeGasto, Incumplimiento } from './gastos'
export type { Leccion, Accion as AccionDeMejora, Borrador as BorradorDeLeccion, Recomendacion, Pendiente as PendienteDeLeccion, Hecho, OrigenLeccion } from './lecciones'
export type { Ficha as FichaDocumental, DocHit, Enlace, DocDetalle, Aprobacion, EstadoProducto, Fuente, Metrica, RespuestaCI } from './conectores'
export { usersApi } from './users'
export type {
  UserListItem,
  UserListParams,
  UserCreatePayload,
  UserUpdatePayload,
  UserProductivityParams,
  UserManagerUpdate,
  ApprovalChainNode,
  UserPublic,
  UserWithRate,
  UserStatus,
  UserOrganization,
  UserSelfUpdatePayload,
} from './users'

export { projectsApi } from './projects'
export type {
  ProjectListItem,
  ProjectListParams,
  ProjectCreatePayload,
  ProjectUpdatePayload,
  PhaseCreatePayload,
  MemberAddPayload,
  ChangelogEntry,
  RaciEntry,
  ProjectDetail,
  ProjectPhase,
  ProjectStatus,
  ProjectType,
  ProjectRisk,
  ProjectPhaseCreatePayload,
} from './projects'

export { tasksApi } from './tasks'
export type {
  TaskStatus,
  TaskListItem,
  TaskListParams,
  TaskCreatePayload,
  TaskUpdatePayload,
  TaskCommentPayload,
  TaskBulkUpdatePayload,
  KanbanResponse,
  MovementLogEntry,
  TaskPriority,
  TaskComment,
  TaskBulkUpdateResult,
} from './tasks'

export { settingsApi } from './settings'
export type {
  GeneralSetting,
  LogLevel,
  LogLevelResponse,
  LogLevelPayload,
  LogLevelChange,
  RuntimeSetting,
  RuntimeFlagsResponse,
  IntegrationProvider,
  IntegrationStatus,
  IntegrationProviderConfig,
  IntegrationField,
  IntegrationFieldUpdate,
  IntegrationTestResult,
  AuditLogParams,
  AuditLogEntry,
} from './settings'
