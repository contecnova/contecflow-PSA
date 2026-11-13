/**
 * Tipos de respuesta de los endpoints mas usados del cliente (_core.ts).
 *
 * Auditoria 2026-11 (#39): _core.ts tenia ~980 llamadas que devolvian
 * AxiosResponse<any>. El backend responde estos recursos con `dict` (no hay
 * esquema de salida en app/schemas: alli solo estan los de entrada, RiskIn,
 * ContractIn, EpicIn, SprintCreate...), asi que los campos de aqui son los que
 * leen las pantallas y los que confirman esos esquemas de entrada; el indice
 * `[extra: string]: unknown` deja leer el resto sin `any`.
 *
 * Las listas llegan ya desenvueltas por el interceptor de _core.ts
 * (APIListResponse `{items, meta}` -> `res.data = items`).
 */

export interface Client {
  id: string
  name?: string
  status?: string
  industry?: string | null
  /** Solo en el detalle (client_service.get_client_detail). */
  projects?: Array<{ id: string; code?: string; name?: string; status?: string }>
  [extra: string]: unknown
}

/** client_service.list_contacts. */
export interface ClientContact {
  id: string
  full_name: string
  email?: string | null
  phone?: string | null
  job_title?: string | null
  role: string
  is_primary?: boolean
  notes?: string | null
  is_active?: boolean
}

/** RiskIn: probability e impact son cualitativos (low/medium/high...). Algunas
 *  vistas calculan con la puntuacion numerica: se aceptan los dos. */
export interface Risk {
  id: string
  title?: string
  description?: string | null
  category?: string | null
  probability?: string | number
  impact?: string | number
  status?: string
  owner_id?: string | null
  cost_impact_min?: number | null
  cost_impact_max?: number | null
  [extra: string]: unknown
}

/** GET /risks/{project_id}: no es una lista, es `{risks, summary}`. */
export interface RiesgosDelProyecto<R = Risk> {
  risks: R[]
  summary: { total: number; open: number; by_level: Record<string, number>; critical_count: number; high_count: number }
}

/** ContractIn / ContractUpdate. */
export interface Contract {
  id: string
  name?: string
  project_id?: string
  client_id?: string
  client_name?: string
  contract_type?: string
  status?: string
  total_amount?: number | null
  hourly_rate?: number | null
  [extra: string]: unknown
}

/** EpicIn / epics_service: la epica tiene `title`, no `name`. */
export interface Epic {
  id: string
  title?: string
  description?: string | null
  color?: string
  status?: string
  priority?: string
  start_date?: string | null
  end_date?: string | null
  [extra: string]: unknown
}

/** SprintCreate / SprintUpdate. */
export interface Sprint {
  id: string
  project_id?: string
  name?: string
  goal?: string | null
  status?: string
  start_date?: string | null
  end_date?: string | null
  [extra: string]: unknown
}

/** cmdb_service.list_sla_calendars (`GET /cmdb/sla-calendars`, lista desenvuelta).
 *  Columnas con valor por defecto (09:00, 18:00, "1,2,3,4,5"): llegan siempre. */
export interface SlaCalendar {
  id: string
  name: string
  timezone: string
  work_start: string
  work_end: string
  /** CSV: 1=lunes ... 7=domingo. */
  work_days: string
  holiday_count?: number
}

/** cmdb_service.create_sla_calendar. */
export interface SlaCalendarCreado { id: string; name: string }
