import { format, formatDistanceToNow } from 'date-fns'
import { es } from 'date-fns/locale'

export type DateInput = Date | string | number | null | undefined
export type Maybe<T> = T | null | undefined

// ── Date helpers ──────────────────────────────────────────────────────────────
export const fmtDate     = (d: DateInput): string => d ? format(new Date(d), 'dd/MM/yyyy', { locale: es }) : '—'
export const fmtDateTime = (d: DateInput): string => d ? format(new Date(d), 'dd/MM/yyyy HH:mm', { locale: es }) : '—'
export const fmtRelative = (d: DateInput): string => d ? formatDistanceToNow(new Date(d), { addSuffix: true, locale: es }) : '—'
export const fmtMonth    = (d: DateInput): string => d ? format(new Date(d), 'MMMM yyyy', { locale: es }) : '—'

export function getWeekStart(date: Date | string | number = new Date()): string {
  const d = new Date(date)
  const day = d.getDay()
  const diff = d.getDate() - day + (day === 0 ? -6 : 1)
  d.setDate(diff)
  return format(d, 'yyyy-MM-dd')
}

// ── Number helpers ────────────────────────────────────────────────────────────
export const fmtCurrency = (n: Maybe<number>, currency?: string | null): string => {
  if (!currency) return new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 }).format(n ?? 0)
  return new Intl.NumberFormat('es-ES', { style: 'currency', currency, maximumFractionDigits: 0 }).format(n ?? 0)
}

export const fmtNumber = (n: Maybe<number>, decimals = 1): string =>
  (n ?? 0).toLocaleString('es-ES', { maximumFractionDigits: decimals })

export const fmtHours = (h: Maybe<number>): string => `${fmtNumber(h ?? 0, 1)}h`

export const fmtPct = (n: Maybe<number>): string => `${fmtNumber(n ?? 0, 1)}%`

// ── Color helpers ─────────────────────────────────────────────────────────────
export function loadColor(pct: number): string {
  if (pct > 100) return 'var(--danger)'
  if (pct > 85)  return 'var(--warning)'
  return 'var(--success)'
}

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export function riskColor(risk: Maybe<string>): string {
  const map: Record<RiskLevel, string> = {
    low: 'var(--success)',
    medium: 'var(--warning)',
    high: 'var(--danger)',
    critical: 'var(--danger)',
  }
  return (risk && (risk in map) ? map[risk as RiskLevel] : undefined) ?? 'var(--text-3)'
}

export function statusColor(status: Maybe<string>): string {
  const map: Record<string, string> = {
    active: 'var(--accent)', planning: 'var(--text-3)', paused: 'var(--warning)',
    closed: 'var(--success)', cancelled: 'var(--danger)',
    todo: 'var(--text-3)', in_progress: 'var(--accent)', done: 'var(--success)',
    blocked: 'var(--danger)', review: 'var(--warning)', backlog: 'var(--surface-5)',
  }
  return (status && map[status]) ?? 'var(--text-3)'
}

// ── File download helper ──────────────────────────────────────────────────────
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

// ── Role helpers ──────────────────────────────────────────────────────────────
export const ROLE_LABELS: Record<string, string> = {
  admin: 'Dirección',
  pm: 'Project Manager',
  team_lead: 'Team Lead',
  hr: 'RRHH',
  employee: 'Empleado',
}

export const PRIORITY_LABELS: Record<string, string> = {
  critical: 'Crítica', high: 'Alta', medium: 'Normal', low: 'Baja',
}

export const STATUS_LABELS: Record<string, string> = {
  planning: 'Planificación', active: 'Activo', paused: 'Pausado',
  closed: 'Cerrado', cancelled: 'Cancelado',
  todo: 'Pendiente', in_progress: 'En curso', done: 'Completada',
  blocked: 'Bloqueada', in_review: 'En revisión', backlog: 'Backlog',
}

export const TYPE_LABELS: Record<string, string> = {
  development: 'Desarrollo', maintenance: 'Mantenimiento',
  rd: 'I+D', internal: 'Interno', consulting: 'Consultoría',
}

// ── Initials ──────────────────────────────────────────────────────────────────
export function initials(name = ''): string {
  return name.split(' ').slice(0, 2).map(w => w[0] ?? '').join('').toUpperCase()
}

// ── Normaliza errores de API (Pydantic 422 devuelve array de objetos) ──────────
// TODO type: shape inferred from axios + FastAPI Pydantic; refine to AxiosError<ApiError>
// once axios is migrated in a later batch.
interface PydanticIssue {
  loc?: unknown
  msg?: unknown
}

export function extractErr(e: unknown, fallback = 'Error inesperado'): string {
  const d = (e as { response?: { data?: { detail?: unknown } } } | null | undefined)?.response?.data?.detail
  if (!d) return fallback
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return (d as PydanticIssue[]).map((item) => {
      const field = Array.isArray(item?.loc) ? item.loc.slice(1).join('.') : ''
      const msg = typeof item?.msg === 'string' ? item.msg : ''
      return field ? `${field}: ${msg}` : msg
    }).filter(Boolean).join(' · ') || fallback
  }
  return String(d) || fallback
}
