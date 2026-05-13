// sharedStatus.ts - Estados y configuración centralizados para portal y backoffice

export interface StatusConfig {
  label: string
  color: string
}

export const STATUS_CFG: Record<string, StatusConfig> = {
  pending:     { label: 'Pendiente',           color: 'var(--text-2)' },
  in_progress: { label: 'En progreso',         color: 'var(--accent)' },
  passed:      { label: 'Aprobado',            color: 'var(--success)' },
  failed:      { label: 'Rechazado',           color: 'var(--danger)' },
  conditional: { label: 'Aprobado con reservas', color: 'var(--warning)' },
  new:           { label: 'Nueva',           color: 'var(--text-2)' },
  reviewing:     { label: 'En revisión',     color: 'var(--accent)' },
  estimated:     { label: 'Presupuestada',   color: 'var(--warning)' },
  approved:      { label: 'Aprobada',        color: 'var(--success)' },
  rejected:      { label: 'Rechazada',       color: 'var(--danger)' },
  in_development:{ label: 'En desarrollo',   color: 'var(--purple)' },
  done:          { label: 'Completada',      color: 'var(--success)' },
  planned:       { label: 'Planificado',     color: 'var(--text-2)' },
  accepted:      { label: 'Aceptado',        color: 'var(--success)' },
  delivered:     { label: 'Entregado',       color: 'var(--purple)' },
  in_review:     { label: 'En revisión',     color: 'var(--warning)' },
}

export const FR_STATUS_CFG: Record<string, StatusConfig> = {
  new:           { label: 'Nueva',           color: 'var(--text-2)' },
  reviewing:     { label: 'En revisión',     color: 'var(--accent)' },
  estimated:     { label: 'Presupuestada',   color: 'var(--warning)' },
  approved:      { label: 'Aprobada',        color: 'var(--success)' },
  rejected:      { label: 'Rechazada',       color: 'var(--danger)' },
  in_development:{ label: 'En desarrollo',   color: 'var(--purple)' },
  done:          { label: 'Completada',      color: 'var(--success)' },
}
