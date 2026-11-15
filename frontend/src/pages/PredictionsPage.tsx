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
import './PredictionsPage.css'

export default function PredictionsPage() {
  const t = useAppT()
  const isMobile = useMediaQuery('(max-width: 900px)')

  return (
    <PageShell className={isMobile ? 'pred-shell-movil' : undefined}>
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

        <div className="pred-row-muted">
          <Bell size={16} className="u-accent" aria-hidden />
          <span>
            {t('predictions_page.alerts_hint_prefix')} <strong>{t('predictions_page.smart_alerts')}</strong> {t('predictions_page.alerts_hint_middle')}{' '}
            <Link to="/alerts" className="pred-enlace">/alerts</Link>, {t('predictions_page.alerts_hint_tab')} <em>{t('predictions_page.intelligent_tab')}</em>.
          </span>
        </div>
      </div>
    </PageShell>
  )
}
