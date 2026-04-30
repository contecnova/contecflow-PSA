/**
 * PageHeader — Cabecera de página consistente con icono, título, breadcrumb, acciones y métricas.
 * Props: title, subtitle, icon, actions, meta, breadcrumb, sticky (fija al scroll).
 */
export default function PageHeader({ title, subtitle, actions, breadcrumb, meta, icon, sticky = false }) {
  return (
    <div className={sticky ? 'sticky-top sticky-top--shadow' : undefined} style={{
      marginBottom: 28,
      paddingTop: sticky ? 16 : 0,
      paddingBottom: 20,
      borderBottom: '1px solid var(--surface-4)',
    }}>
      {/* Breadcrumb */}
      {breadcrumb && (
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 10 }}>
          {breadcrumb.map((crumb, i) => (
            <span key={i} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              {i > 0 && <span style={{ color: 'var(--text-4)', fontSize: "var(--text-xs)" }}>›</span>}
              {crumb.onClick ? (
                <button type="button" style={{
                  fontSize: "var(--text-xs)", fontWeight: 500, color: i === breadcrumb.length - 1 ? 'var(--text-2)' : 'var(--accent)',
                  cursor: 'pointer', textTransform: 'uppercase', letterSpacing: '0.06em',
                  background: 'none', border: 'none', padding: 0, fontFamily: 'inherit',
                }} onClick={crumb.onClick}>{crumb.label}</button>
              ) : (
                <span style={{
                  fontSize: "var(--text-xs)", fontWeight: 500, color: i === breadcrumb.length - 1 ? 'var(--text-2)' : 'var(--accent)',
                  textTransform: 'uppercase', letterSpacing: '0.06em',
                }}>{crumb.label}</span>
              )}
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
              fontSize: "var(--text-xl-em)", fontWeight: 700, color: 'var(--text-1)',
              letterSpacing: '-0.01em', lineHeight: 1.2, margin: 0,
            }}>
              {title}
            </h1>
          </div>
          {subtitle && (
            <p style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', margin: '8px 0 0', fontWeight: 400, paddingLeft: icon ? 46 : 0 }}>
              {subtitle}
            </p>
          )}
          {/* Meta tags */}
          {meta && meta.length > 0 && (
            <div style={{ display: 'flex', gap: 12, marginTop: 10, flexWrap: 'wrap', paddingLeft: icon ? 46 : 0 }}>
              {meta.map((m, i) => (
                <div key={i} style={{ display: 'flex', gap: 5, alignItems: 'center', fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
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
