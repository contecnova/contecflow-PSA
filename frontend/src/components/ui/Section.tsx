import type { ReactNode } from 'react'

/**
 * <Section> — bloque semántico con cabecera (título + subtítulo + acciones)
 * y contenido.
 */
export interface SectionProps {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children?: ReactNode
  className?: string
  eyebrow?: boolean
}

export default function Section({
  title,
  subtitle,
  actions,
  children,
  className = '',
  eyebrow = false,
}: SectionProps) {
  return (
    <section className={`ds-section ${className}`.trim()}>
      {(title || subtitle || actions) && (
        <header className="ds-section__head">
          <div className="ds-stack-sm u-min0">
            {title && (eyebrow
              ? <div className="ds-eyebrow">{title}</div>
              : <h3 className="ds-section__title">{title}</h3>
            )}
            {subtitle && <div className="ds-section__subtitle">{subtitle}</div>}
          </div>
          {actions && <div className="ds-row-wrap">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}
