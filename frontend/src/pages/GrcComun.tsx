// Catalogos y utilidades compartidos por las pestañas de GRC (modulos, acciones, roles, colores). 23-11-2026: troceado de GrcPage sin cambio de comportamiento.
import { useQuery } from '@tanstack/react-query'
import { grcApi } from '../services/api'
import type { PermisosGrc } from '../services/api/tipos-grc'
import { useAppT } from '../i18n/AppLangContext'

// ── Catálogo de módulos, acciones y roles ────────────────────────────────────
// Revisión GRC 2026-11b: los módulos los da la API (`/grc/permissions` →
// `modules`, derivados de las rutas). Antes había 15 escritos aquí, dos de
// ellos (`service_desk`, `hr`) sin ninguna ruta detrás, y los otros ~95 que la
// matriz sí aplica no se podían ver ni tocar. Esto sólo pone nombre e icono.
export const MODULE_LABELS: Record<string, { label: string }> = {
  projects:   { label: 'pagina_grc.proyectos' },
  tasks:      { label: 'pagina_grc.tareas' },
  timesheets: { label: 'pagina_grc.timesheets' },
  invoices:   { label: 'pagina_grc.facturacion' },
  expenses:   { label: 'pagina_grc.gastos' },
  resources:  { label: 'pagina_grc.recursos' },
  sd:         { label: 'pagina_grc.service_desk' },
  contracts:  { label: 'pagina_grc.contratos' },
  clients:    { label: 'pagina_grc.clientes_crm' },
  reports:    { label: 'pagina_grc.informes_bi' },
  settings:   { label: 'pagina_grc.configuracion' },
  approvals:  { label: 'pagina_grc.aprobaciones' },
  alm:        { label: 'pagina_grc.alm_activos' },
  absences:   { label: 'pagina_grc.ausencias' },
  grc:        { label: 'pagina_grc.grc_seguridad' },
}

type Traductor = ReturnType<typeof useAppT>

export const moduleInfo = (t: Traductor) => (id?: string) => {
  const m = MODULE_LABELS[id || '']
  return { id: id || '', label: m ? t(m.label) : id || '' }
}

/** La matriz efectiva con sus módulos y roles, como la devuelve la API (caché compartida). */
export function usePermisos() {
  return useQuery<PermisosGrc>({
    queryKey: ['grc-permissions'],
    queryFn: () => grcApi.permissions().then(r => r.data),
  })
}

/** Reserva por si la API no manda `actions` (el vocabulario es `grc_catalog.GRC_ACTIONS`). */
export const ACTIONS = ['ver', 'crear', 'editar', 'eliminar', 'aprobar', 'exportar']

const ACTION_LABEL: Record<string, string> = { ver: 'pagina_grc.ver', crear: 'pagina_grc.crear', editar: 'pagina_grc.editar', eliminar: 'pagina_grc.eliminar', aprobar: 'pagina_grc.aprobar', exportar: 'pagina_grc.exportar' }

export type Role = { id: string; label: string; color: string }

// ROLES se carga dinámicamente desde la API — ver useRoles() en GrcPage
const FALLBACK_ROLES = [
  { id: 'admin',     label: 'pagina_grc.admin',      color: 'var(--accent)' },
  { id: 'pm',        label: 'pagina_grc.pm',  color: 'var(--purple)' },
  { id: 'team_lead', label: 'pagina_grc.team_lead',  color: 'var(--sky-blue)' },
  { id: 'employee',  label: 'pagina_grc.employee',   color: 'var(--success)' },
  { id: 'hr',        label: 'pagina_grc.hr',  color: 'var(--warning)' },
  { id: 'subcontractor', label: 'pagina_grc.subcontratado', color: 'var(--orange)' },
]

/** FALLBACK_ROLES con el nombre ya traducido. */
export const rolesDeReserva = (t: Traductor): Role[] => FALLBACK_ROLES.map(r => ({ ...r, label: t(r.label) }))

export const RISK_COLOR: Record<string, string> = { critical: 'var(--danger)', high: 'var(--orange)', medium: 'var(--warning)', low: 'var(--success)' }

/** Niveles de riesgo de una regla SoD (`schemas.grc.NivelDeRiesgo`). */
export const RIESGOS = ['critical', 'high', 'medium', 'low'] as const

/** Texto de una acción GRC (con reserva al código si no es del vocabulario). */
export const accionDe = (t: Traductor) => (a?: string) => ACTION_LABEL[a || ''] ? t(ACTION_LABEL[a || '']) : (a || '')

export const SEV_COLOR: Record<string, string>  = { critical: 'var(--danger)', warning: 'var(--warning)', info: 'var(--info)' }
