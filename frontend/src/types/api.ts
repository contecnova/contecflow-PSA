/**
 * Tipos compartidos para respuestas de la API Contecflow PSA.
 *
 * Audit #115 — base para la migración gradual a TypeScript.
 * Estos tipos describen los shapes más comunes que devuelve el backend
 * FastAPI para evitar `any` en los hooks/services principales.
 */

// ── Auth ────────────────────────────────────────────────────────────────

export interface User {
  id: string
  username: string
  email: string
  full_name?: string | null
  role: UserRole
  is_active: boolean
  is_superadmin?: boolean
  organization_id?: string | null
  department?: string | null
  hourly_rate?: number | null
}

export type UserRole = 'admin' | 'pm' | 'employee' | 'hr' | 'finance' | 'sales' | 'client'

export interface Organization {
  id: string
  name: string
  slug: string
  plan: string
  is_active: boolean
  require_mfa?: boolean
}

export interface AuthTokens {
  access_token: string
  refresh_token?: string
  token_type: 'bearer'
}

// ── Pagination ─────────────────────────────────────────────────────────

export interface PageMeta {
  page: number
  page_size: number
  total?: number
  total_pages?: number
}

export interface Paginated<T> {
  items: T[]
  meta?: PageMeta
}

// ── Generic API envelope ───────────────────────────────────────────────

export interface ApiError {
  detail: string | Record<string, unknown>
  code?: string
  status?: number
}

// ── Project domain ─────────────────────────────────────────────────────

export type ProjectStatus = 'planning' | 'active' | 'on_hold' | 'completed' | 'cancelled'

export interface Project {
  id: string
  name: string
  code: string
  status: ProjectStatus
  description?: string | null
  client_id?: string | null
  billing_type?: string
  is_billable?: boolean
  start_date?: string | null
  end_date_planned?: string | null
  is_active: boolean
}

// ── Task domain ────────────────────────────────────────────────────────

export type TaskStatus = 'backlog' | 'todo' | 'in_progress' | 'blocked' | 'in_review' | 'done' | 'cancelled'
export type TaskPriority = 'critical' | 'high' | 'medium' | 'low'

export interface Task {
  id: string
  code: string
  title: string
  description?: string | null
  status: TaskStatus
  priority: TaskPriority
  project_id: string
  assignee_id?: string | null
  reporter_id?: string | null
  estimated_hours?: number | null
  story_points?: number | null
  start_date?: string | null
  due_date?: string | null
}
