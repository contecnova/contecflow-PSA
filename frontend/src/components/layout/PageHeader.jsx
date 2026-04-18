/**
 * PageHeader — Cabecera de página consistente con icono, título, breadcrumb, acciones y métricas
 * Acepta un prop `icon` (elemento Lucide/JSX) que se muestra junto al título.
 */
// subtitle debe ser SIEMPRE una cadena traducida (ej: t('modulo.subtitle'))
export default function PageHeader({ title, subtitle, actions, breadcrumb, meta, icon }) {
  return (
    <div style={{
      marginBottom: 28,
      paddingBottom: 20,
      borderBottom: '1px solid var(--surface-4)',
    }}>
      {/* Breadcrumb */}
      {breadcrumb && (
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 10 }}>
          {breadcrumb.map((crumb, i) => (
            <span key={i} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              {i > 0 && <span style={{ color: 'var(--text-4)', fontSize: 11 }}>›</span>}
              <span style={{
                fontSize: 11, fontWeight: 500, color: i === breadcrumb.length - 1 ? 'var(--text-2)' : 'var(--accent)',
                cursor: crumb.onClick ? 'pointer' : 'default',
                textTransform: 'uppercase', letterSpacing: '0.06em',
              }} onClick={crumb.onClick}>{crumb.label}</span>
            </span>
          ))}
        </div>
      )}

      {/* Título + acciones */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {icon && (
              <div style={{
                width: 36, height: 36, borderRadius: 10,
                background: 'var(--accent-muted)', border: '1px solid rgba(79,142,247,0.25)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'var(--accent)', flexShrink: 0,
              }}>
                {icon}
              </div>
            )}
            <h1 style={{
              fontSize: 22, fontWeight: 700, color: 'var(--text-1)',
              letterSpacing: '-0.01em', lineHeight: 1.2, margin: 0,
            }}>
              {title}
            </h1>
          </div>
          {subtitle && (
            <p style={{ fontSize: 13, color: 'var(--text-2)', margin: '8px 0 0', fontWeight: 400, paddingLeft: icon ? 46 : 0 }}>
              {subtitle}
            </p>
          )}
          {/* Meta tags */}
          {meta && meta.length > 0 && (
            <div style={{ display: 'flex', gap: 12, marginTop: 10, flexWrap: 'wrap', paddingLeft: icon ? 46 : 0 }}>
              {meta.map((m, i) => (
                <div key={i} style={{ display: 'flex', gap: 5, alignItems: 'center', fontSize: 12, color: 'var(--text-2)' }}>
                  {m.icon && <span style={{ opacity: 0.7 }}>{m.icon}</span>}
                  <span style={{ color: m.color || 'var(--text-2)' }}>{m.value}</span>
                  {m.label && <span style={{ color: 'var(--text-3)' }}>{m.label}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
        {/* Actions slot */}
        {actions && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
            {actions}
          </div>
        )}
      </div>
    </div>
  )
}
