/**
 * SupportDashboardPage — Panel de soporte (estado del soporte e ITSM).
 * Reutiliza MetricsDashboardTab con el mismo diseño visual.
 *
 * 16-11-2026: cabecera estándar (PageShell + PageHeader con icono, título del
 * menú y subtítulo traducido). Antes la página era solo MetricsDashboardTab,
 * cuya cabecera propia no tiene icono, usa un título menor y no lleva
 * separador. El contenido (MetricsDashboardTab, de service-desk) ya no trae
 * cabecera ni PageShell propios: va directamente bajo esta cabecera.
 */
import { LayoutGrid } from 'lucide-react'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { useAppT } from '../i18n/AppLangContext'
import MetricsDashboardTab from './service-desk/MetricsDashboardTab'
import './SupportDashboardPage.css'

export default function SupportDashboardPage() {
  const t = useAppT()
  return (
    <PageShell>
      <PageHeader
        icon={<LayoutGrid size={18} />}
        title={t('nav.support_dashboard')}
        subtitle={t('support_dashboard_page.subtitulo')}
        showListExport={false}
      />
      <div className="sdash-cuerpo">
        <MetricsDashboardTab />
      </div>
    </PageShell>
  )
}
