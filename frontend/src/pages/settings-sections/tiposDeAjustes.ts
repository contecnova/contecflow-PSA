/**
 * Tipos de formularios y filas compartidos por las secciones de Configuración.
 * Troceado de SettingsPageSections.tsx sin cambio de comportamiento (23-11-2026).
 */
import type { ChangeEvent } from 'react'
import type { UserPublic } from '../../services/api'

// ── Tipos ─────────────────────────────────────────────────────────────────────
// Formas de lo que devuelve la API para cada sección (app/schemas/** y los
// serializadores de app/services/advanced_config_service.py) y del estado local
// de los formularios. Se declaran con `type` (no `interface`) para que sigan
// siendo asignables a `Record<string, unknown>`, que es lo que piden los
// métodos de escritura de settingsApi/advancedConfigApi.


/** Usuario del listado (`UserPublic`). `GET /users` no manda `hourly_rate` (es
 *  confidencial): la ficha de edición la completa con `GET /users/{id}` (`UserWithRate`). */
export type UserRow = UserPublic & {
  hourly_rate?: number | null
  /** Rev. 166 (#27): grado o categoría profesional (ámbito y condiciones de las políticas). */
  grade?: string | null
}

export type UserFormValues = {
  username: string
  email: string
  full_name: string
  role: string
  department: string
  job_title: string
  grade: string
  // Los <input type="number"> dejan aquí el texto tal cual.
  weekly_capacity_hours: number | string
  hourly_rate: number | string
  timezone: string
  organization_ids: string[]
  organization_id: string
  custom_role_id: string
  password: string
}

/** Sin superadmin el formulario no envía las empresas. */
export type UserFormPayload = UserFormValues | Omit<UserFormValues, 'organization_ids' | 'organization_id'>

export type RoleForm = { name: string; description: string; color: string; module_access: Record<string, unknown> }

export type NotifyKey = 'notify_admin' | 'notify_pm' | 'notify_hr' | 'notify_employee' | 'notify_email'

export type AlertConfig = {
  alert_type: string
  label: string
  description?: string | null
  severity: string
  is_enabled: boolean
  threshold_value: number | null
  threshold_unit?: string | null
} & Partial<Record<NotifyKey, boolean>>

export type RuleForm = { name: string; metric_key: string; condition: string; threshold: string | number; severity: string; cooldown_minutes: string | number }

export type VacationBalance = { user_id: string; user_name: string; department?: string | null; days_entitled: number; days_taken: number; days_pending: number; days_remaining: number }

export type NumberingSeq = { entity: string; prefix: string; separator: string; padding: number; include_year: boolean; current_value: number; next_preview: string }

export type CustomField = { id: string; entity: string; name: string; field_key: string; field_type: string; is_required: boolean; placeholder?: string | null }

export type CustomFieldEdit = { name: string; is_required: boolean; placeholder: string }

export type CustomFieldForm = { entity: string; name: string; field_key: string; field_type: string; is_required: boolean; placeholder: string }

export type Office = { id: string; name: string; country?: string | null; city?: string | null; timezone?: string | null }

export type OfficeForm = { name: string; country: string; city: string; timezone: string }

export type DepartmentForm = { name: string; description: string; area_id: string }

export type MetricForm = { label: string; description: string; operand_a: string; operator: string; operand_b_type: string; operand_b: string; scale: string | number }

export type InputChange = ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
