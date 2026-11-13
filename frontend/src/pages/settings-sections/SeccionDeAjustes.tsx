import type { ReactNode } from 'react'

/**
 * Bloque de una pantalla de Ajustes: tarjeta con icono, titulo y descripcion.
 * Auditoria 2026-11 (#41): estaba copiado en SettingsPageSections y
 * SettingsAdvancedSections (con estilos distintos); una sola version.
 */
export default function SeccionDeAjustes({ icon, title, description, children }: { icon?: ReactNode; title?: ReactNode; description?: ReactNode; children?: ReactNode }) {
  return (
    <div className="ds-card" style={{ marginBottom: 'var(--space-6)' }}>
      <div className="ds-stack-sm" style={{ marginBottom: 'var(--space-3)' }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
          fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--text-1)',
        }}>
          {icon && <span style={{ display: 'inline-flex', alignItems: 'center', color: 'var(--accent)' }}>{icon}</span>}
          <span>{title}</span>
        </div>
        {description && <div className="ds-muted">{description}</div>}
      </div>
      {children}
    </div>
  )
}
