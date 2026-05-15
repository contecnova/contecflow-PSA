import type { ReactNode } from 'react'
// TODO type: layout/* still JS.
import PageHeader from '../layout/PageHeader'
import PageShell from '../layout/PageShell'

/**
 * <Page> — wrapper de página unificado.
 *
 * Compone PageShell + PageHeader + un body en stack. Usar en lugar de
 * volver a montarlos manualmente en cada página.
 */
export interface PageProps {
  icon?: ReactNode
  title?: ReactNode
  subtitle?: ReactNode
  rightActions?: ReactNode
  /** alias compatible (PageHeader nativo usa 'actions') */
  actions?: ReactNode
  children?: ReactNode
}

export default function Page({
  icon,
  title,
  subtitle,
  rightActions,
  actions,
  children,
}: PageProps) {
  // PageHeader espera la prop con nombre 'actions'. Aceptamos ambos nombres
  // para mantener compatibilidad con páginas migradas que usaron rightActions.
  const headerActions = rightActions ?? actions
  return (
    <PageShell>
      {(title || icon || headerActions) && (
        <PageHeader
          icon={icon}
          title={title}
          subtitle={subtitle}
          actions={headerActions}
        />
      )}
      <div className="ds-page">{children}</div>
    </PageShell>
  )
}
