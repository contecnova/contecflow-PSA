import type { CSSProperties, ReactNode } from 'react'
import './PageShell.estilos.css'
import { useIncrustadaEnAjustes } from './incrustacion'

/**
 * PageShell — contenedor estándar de página con padding y max-width consistentes.
 *
 *   <PageShell>
 *     <PageHeader title="..." />
 *     ...
 *   </PageShell>
 *
 * Aplica los tokens `--page-pad-x`, `--page-pad-y`, `--page-max-w` definidos en
 * index.css. Equivale a la clase `.page-content` pero como componente para
 * forzar consistencia y permitir variantes (`maxWidth="full"`, `dense`).
 *
 * Variantes:
 *   - `maxWidth="full"` quita el `max-width` (útil para canvas full-bleed).
 *   - `dense` reduce el padding vertical.
 */
interface Props {
  children?: ReactNode
  maxWidth?: 'default' | 'full'
  dense?: boolean
  style?: CSSProperties
  className?: string
}

export default function PageShell({ children, maxWidth = 'default', dense = false, style, className = '' }: Props) {
  // 18-11-2026: dentro de Configuración el relleno y el ancho los pone la pantalla de ajustes.
  if (useIncrustadaEnAjustes()) {
    return <div className={`page-shell--incrustada ${className}`.trim()} style={style || {}}>{children}</div>
  }
  return (
    <div
      className={`${`page-content ${className}`.trim() || ''} ${maxWidth === 'full' ? 'page-shell-m1' : ''} ${dense ? 'page-shell-m2' : ''}`}
      style={style || {}}
    >
      {children}
    </div>
  )
}
