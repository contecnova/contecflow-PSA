// Constantes, tipos y utilidades compartidos por la pantalla de subcontratistas. 23-11-2026: troceado de SubcontractorsPage sin cambio de comportamiento.
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import type { SkillDelCatalogo, SubFactura, SubParteDeHoras, SubTrabajador, Subcontratista } from '../services/api/tipos-alm'
import type { StatusBadgeKind } from '../components/ui/StatusBadge'

/** Estados de factura de subcontratista y niveles de skill: su color sale de la clase. */
export const ESTADOS_FACTURA = ['received', 'approved', 'paid', 'rejected']

export const NIVELES = ['basic', 'intermediate', 'advanced', 'expert']

export const claseNivel = (nivel: string) => NIVELES.includes(nivel) ? ` sub-skill--${nivel}` : ''

export const TIPO_FACTURA: Record<string, StatusBadgeKind> = { received: 'warning', approved: 'accent', paid: 'success', rejected: 'danger' }

// Respuestas de /enterprise/subcontractors* y /skills/catalog: services/api/tipos-alm.
export type Skill = SkillDelCatalogo

export type Worker = SubTrabajador

export type Sub = Subcontratista

export type Timelog = SubParteDeHoras

export type Invoice = SubFactura

export type CredsInfo = { username: string; password?: string }

/** Papel en el proyecto de la asignación (ProjectMember.role). */
export const PAPELES = ['lead', 'developer', 'designer', 'qa', 'analyst', 'devops', 'stakeholder', 'other']

export function onKeyboardActivate(event: ReactKeyboardEvent, action: () => void) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}
