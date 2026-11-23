/**
 * Tipos, constantes y esquemas compartidos de la página de proyectos.
 * Troceado de ProjectsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import type { ComponentProps } from 'react'
import type GanttChart from '../../components/GanttChart'
import type { useAppT } from '../../i18n/AppLangContext'
import { z } from 'zod'

export const PROJ_COLS = [
  { id: 'name',     label: 'proyectos_ui.col_proyecto',     width: '2fr',   sortKey: 'name' },
  { id: 'type',     label: 'proyectos_ui.col_tipo',     width: '1fr',   sortKey: 'project_type' },
  { id: 'pm',       label: 'proyectos_ui.col_pm',     width: '1fr',   sortKey: 'pm_name' },
  { id: 'status',   label: 'proyectos_ui.col_estado',     width: '140px', sortKey: 'status' },
  { id: 'budget',   label: 'proyectos_ui.col_presupuesto',  width: '100px', sortKey: 'budget_used_pct' },
  { id: 'progress', label: 'proyectos_ui.col_progreso',     width: '80px',  sortKey: 'progress_pct' },
  { id: 'risk',     label: 'proyectos_ui.col_riesgo',     width: '80px',  sortKey: 'risk_level' },
]

export type Traductor = ReturnType<typeof useAppT>
/** Cambio de un campo de texto, select, textarea o DateInput. */
export type CambioDeCampo = { target: { value: string } }

/** `ProjectSummary` (app/schemas/projects.py): una fila del listado. `task_count` lo lee la tarjeta aunque el esquema no lo declara. */
export type ProjectSummary = {
  id: string
  code: string
  name: string
  status: string
  project_type?: string
  risk_level?: string
  pm_name?: string | null
  client_name?: string | null
  department?: string | null
  budget_amount?: number | null
  total_cost_spent?: number | null
  budget_used_pct?: number | null
  progress_pct?: number | null
  team_size?: number
  task_count?: number
  start_date?: string | null
  end_date_planned?: string | null
}
export type ProjectPhase = { id: string; name: string; start_date?: string | null; end_date?: string | null; status?: string }
/** `ProjectOut` (app/schemas/projects.py): el detalle. No trae las tareas: el Gantt por proyecto
 *  las pide aparte a `GET /tasks?project_id=`. */
export type ProjectDetail = ProjectSummary & {
  description?: string | null
  client_id?: string | null
  billing_type?: string | null
  /** Importe del contrato (moneda de la empresa): base de los hitos por % (A-MP10). */
  contract_amount?: number | null
  retainer_amount?: number | null
  retainer_day?: number | null
  project_manager?: { full_name: string } | null
  phases?: ProjectPhase[]
  tasks_total?: number
  tasks_done?: number
}
export type ProjectForm = {
  name: string
  project_type: string
  status: string
  client_name: string
  department: string
  budget_amount: string | number
  contract_amount: string | number
  description: string
  risk_level: string
  start_date: string
  end_date_planned: string
  client_id: string
  billing_type: string
  retainer_amount: string | number
  retainer_day: string | number
}
/** Al subcontratado le llegan sin correo ni dedicación (`politica_de_visibilidad`, segunda auditoría 2026-11). */
export type ProjectMember = { id: string; user_id: string; full_name: string; email?: string; role: string; allocation_pct?: number; avatar_initials?: string; external_company?: string | null }
/** Solicitud de mejora del portal (`/portal/feature-requests/team`). */
export type FeatureRequest = {
  id: string
  code?: string
  title: string
  description?: string | null
  business_justification?: string | null
  client_approved?: boolean
  priority?: string
  status: string
  pm_response?: string | null
  estimated_hours?: number | null
  estimated_cost?: number | null
  estimated_delivery_weeks?: number | null
  submitted_at?: string | null
}
export type RespondForm = { pm_response: string; estimated_hours: string | number; estimated_cost: string | number; estimated_delivery_weeks: string | number; status: string }
export type RespondBody = { pm_response?: string; estimated_hours?: number; estimated_cost?: number; estimated_delivery_weeks?: number; status: string }
// Alta de plantilla (TemplateCreate): las fases y tareas son dicts; el servicio lee
// `estimated_weeks` de cada fase y `estimated_hours` de cada tarea (billing_reports_service/plantillas.py).
export type NewTemplatePhase = { name: string; estimated_weeks: number; tasks: Array<{ title: string; estimated_hours: number }> }
export type NewTemplate = { name: string; description: string; project_type: string; estimated_weeks: number; estimated_hours?: number; phases: NewTemplatePhase[] }
export type InstantiateForm = { name: string; client_id: string; client_name: string; start_date: string; budget_amount: string; pm_id?: string }
export type GanttTasks = ComponentProps<typeof GanttChart>['tasks']

// ── Estilos compartidos ───────────────────────────────────────────────────────


export const PROJECT_STATUSES = [
  { value: 'planning',  label: 'proyectos_ui.estado_planning' },
  { value: 'active',    label: 'proyectos_ui.estado_active' },
  { value: 'on_hold',   label: 'proyectos_ui.estado_on_hold' },
  { value: 'paused',    label: 'proyectos_ui.estado_paused' },
  { value: 'completed', label: 'proyectos_ui.estado_completed' },
  { value: 'closed',    label: 'proyectos_ui.estado_closed' },
  { value: 'cancelled', label: 'proyectos_ui.estado_cancelled' },
  { value: 'archived',  label: 'proyectos_ui.estado_archived' },
]
// 19-11-2026: los tipos de proyecto salen del catálogo de la empresa (`/settings/project-types`).
export const RISK_LEVELS = [
  { value: 'low', label: 'proyectos_ui.riesgo_low' },
  { value: 'medium', label: 'proyectos_ui.riesgo_medium' },
  { value: 'high', label: 'proyectos_ui.riesgo_high' },
  { value: 'critical', label: 'proyectos_ui.riesgo_critical' },
]

export function makeProjectFormSchema(t: Traductor) {
  return z.object({
    name: z.string().min(1, t('projects.error_name_required')),
    project_type: z.string().min(1, t('projects.error_type_required')),
    start_date: z.string().optional(),
    end_date_planned: z.string().optional(),
    budget_amount: z.union([z.string(), z.number(), z.null()]).optional(),
    contract_amount: z.union([z.string(), z.number(), z.null()]).optional(),
    retainer_amount: z.union([z.string(), z.number(), z.null()]).optional(),
    retainer_day: z.union([z.string(), z.number(), z.null()]).optional(),
    billing_type: z.string().optional(),
  }).superRefine((data, ctx) => {
    if (data.start_date && data.end_date_planned && data.end_date_planned < data.start_date) {
      ctx.addIssue({ code: 'custom', path: ['end_date_planned'], message: t('projects.error_date_range') })
    }
    const budget = Number(data.budget_amount || 0)
    if (!Number.isNaN(budget) && budget < 0) {
      ctx.addIssue({ code: 'custom', path: ['budget_amount'], message: t('projects.error_budget_negative') })
    }
    const contrato = Number(data.contract_amount || 0)
    if (!Number.isNaN(contrato) && contrato < 0) {
      ctx.addIssue({ code: 'custom', path: ['contract_amount'], message: t('projects.error_budget_negative') })
    }
    const retainerDay = Number(data.retainer_day || 0)
    if (data.billing_type === 'recurring_retainer' && (retainerDay < 1 || retainerDay > 28)) {
      ctx.addIssue({ code: 'custom', path: ['retainer_day'], message: t('projects.error_retainer_day') })
    }
  })
}

export function makeProjectMemberSchema(t: Traductor) {
  return z.object({
    user_id: z.string().trim().min(1, t('projects.error_person_required')),
    role: z.string().trim().min(1, t('projects.error_role_required')),
    allocation_pct: z.coerce.number()
      .min(1, t('projects.error_allocation'))
      .max(100, t('projects.error_allocation')),
    notes: z.string().optional(),
  })
}

export const MEMBER_ROLES: Record<string, string> = {
  lead: 'proyectos_ui.rol_lead', developer: 'proyectos_ui.rol_developer', designer: 'proyectos_ui.rol_designer',
  qa: 'proyectos_ui.rol_qa', analyst: 'proyectos_ui.rol_analyst', devops: 'proyectos_ui.rol_devops',
  stakeholder: 'proyectos_ui.rol_stakeholder', other: 'proyectos_ui.rol_other',
}
