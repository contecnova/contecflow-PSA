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
export default function PageShell({ children, maxWidth = 'default', dense = false, style, className = '' }) {
  return (
    <div
      className={`page-content ${className}`.trim()}
      style={{
        ...(maxWidth === 'full' ? { maxWidth: 'none' } : null),
        ...(dense ? { paddingTop: 'calc(var(--page-pad-y) / 2)', paddingBottom: 'calc(var(--page-pad-y) / 2)' } : null),
        ...(style || {}),
      }}
    >
      {children}
    </div>
  )
}
