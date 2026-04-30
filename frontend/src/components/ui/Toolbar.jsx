/**
 * Toolbar — barra de filtros + acciones para páginas tipo lista.
 *
 *   <Toolbar
 *     left={<><SearchInput/><FilterSelect.../></>}
 *     right={<Button>Nuevo</Button>}
 *     dense
 *   />
 *
 * Slots:
 *   - left:  filtros (search, selects, chips). Hace flex-wrap automático.
 *   - right: acciones primarias (CTAs, botón "Nuevo", export).
 *   - children: alternativa libre si no necesitas la separación left/right.
 *
 * Defaults: gap consistente, alineación vertical centrada, margin-bottom estándar.
 */
export default function Toolbar({ left, right, children, dense = false, style, className }) {
  return (
    <div
      role="toolbar"
      className={className}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: dense ? 8 : 12,
        flexWrap: 'wrap',
        marginBottom: dense ? 12 : 16,
        ...(style || {}),
      }}
    >
      {children ?? (
        <>
          {left && (
            <div style={{ display: 'flex', alignItems: 'center', gap: dense ? 6 : 8, flexWrap: 'wrap', flex: 1, minWidth: 0 }}>
              {left}
            </div>
          )}
          {right && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, marginLeft: 'auto' }}>
              {right}
            </div>
          )}
        </>
      )}
    </div>
  )
}
