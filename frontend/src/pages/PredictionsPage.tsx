/**
 * PredictionsPage — Inteligencia predictiva.
 * Forecasting con ML, detección de anomalías y entrega condicional.
 * Antes vivía en /bi tab "intelligence". Smart Alerts BI se ha trasladado a /alerts.
 */
import PageShell from '../components/layout/PageShell'
import PageHeader from '../components/layout/PageHeader'
import { Brain, Bell } from 'lucide-react'
import { Link } from 'react-router-dom'
import useMediaQuery from '../hooks/useMediaQuery'
import BiForecastingPanel from '../components/bi/BiForecastingPanel'
import BiAnomalyPanel from '../components/bi/BiAnomalyPanel'
import BiConditionalDeliveryPanel from '../components/bi/BiConditionalDeliveryPanel'
import { useAppT } from '../i18n/AppLangContext'

export default function PredictionsPage() {
  const t = useAppT()
  const isMobile = useMediaQuery('(max-width: 900px)')

  return (
    <PageShell style={isMobile ? { paddingLeft: 14, paddingRight: 14 } : undefined}>
      <PageHeader
        icon={<Brain size={18} />}
        title={t('predictions_page.title')}
        subtitle={t('predictions_page.subtitle')}
      showListExport={false}
      />

      <div className="u-stack-20">
        <BiForecastingPanel />
        <BiAnomalyPanel />
        <BiConditionalDeliveryPanel />

        <div style={{
          background: 'var(--surface-2)', border: '1px dashed var(--surface-4)', borderRadius: 12,
          padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 10, fontSize: 'var(--text-sm)', color: 'var(--text-2)',
        }}>
          <Bell size={16} style={{ color: 'var(--accent)' }} />
          <span>
            {t('predictions_page.alerts_hint_prefix')} <strong>{t('predictions_page.smart_alerts')}</strong> {t('predictions_page.alerts_hint_middle')}{' '}
            <Link to="/alerts" style={{ color: 'var(--accent)', textDecoration: 'underline' }}>/alerts</Link>, {t('predictions_page.alerts_hint_tab')} <em>{t('predictions_page.intelligent_tab')}</em>.
          </span>
        </div>
      </div>
    </PageShell>
  )
}
