/**
 * <Section> — bloque semántico con cabecera (título + subtítulo + acciones)
 * y contenido. Reemplaza patrones inline tipo:
 *
 *   <div style={{ marginBottom: 18 }}>
 *     <div style={{ ...eyebrow }}>Miembros</div>
 *     <button>+ Añadir</button>
 *     {children}
 *   </div>
 *
 * por:
 *
 *   <Section title="Miembros" actions={<button>+ Añadir</button>}>
 *     {children}
 *   </Section>
 */
export default function Section({
  title,
  subtitle,
  actions,
  children,
  className = '',
  eyebrow = false,
}) {
  return (
    <section className={`ds-section ${className}`.trim()}>
      {(title || subtitle || actions) && (
        <header className="ds-section__head">
          <div className="ds-stack-sm" style={{ minWidth: 0 }}>
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
