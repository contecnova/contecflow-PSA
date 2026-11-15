import type { ReactNode } from 'react'
import './SeccionDeAjustes.css'

/**
 * Bloque de una pantalla de Ajustes: tarjeta con icono, titulo y descripcion.
 * Auditoria 2026-11 (#41): estaba copiado en SettingsPageSections y
 * SettingsAdvancedSections (con estilos distintos); una sola version.
 */
export default function SeccionDeAjustes({ icon, title, description, children }: { icon?: ReactNode; title?: ReactNode; description?: ReactNode; children?: ReactNode }) {
  return (
    <div className="ds-card sedeaj-sp-1">
      <div className="ds-stack-sm sedeaj-sp-2">
        <div className="sedeaj-row-1">
          {icon && <span className="sedeaj-row-2">{icon}</span>}
          <span>{title}</span>
        </div>
        {description && <div className="ds-muted">{description}</div>}
      </div>
      {children}
    </div>
  )
}
