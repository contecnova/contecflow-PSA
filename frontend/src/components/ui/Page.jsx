/**
 * <Page> — wrapper de página unificado.
 *
 * Compone PageShell + PageHeader + un body en stack. Usar en lugar de
 * volver a montarlos manualmente en cada página.
 */
import PageHeader from '../layout/PageHeader'
import PageShell from '../layout/PageShell'

export default function Page({
  icon,
  title,
  subtitle,
  rightActions,
  children,
}) {
  return (
    <PageShell>
      {(title || icon || rightActions) && (
        <PageHeader
          icon={icon}
          title={title}
          subtitle={subtitle}
          rightActions={rightActions}
        />
      )}
      <div className="ds-page">{children}</div>
    </PageShell>
  )
}
