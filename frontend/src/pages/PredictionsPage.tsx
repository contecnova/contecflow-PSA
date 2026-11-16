/**
 * PredictionsPage — Inteligencia predictiva.
 * Previsión de métricas, detección de anomalías y envío condicional de informes.
 * Antes vivía en /bi tab "intelligence". Smart Alerts BI se ha trasladado a /alerts.
 *
 * 16-11-2026: pasada de diseño. Título del menú, subtítulo sin anglicismos y la
 * nota de alertas como tarjeta normal con enlace por nombre (antes una caja
 * discontinua con la ruta «/alerts» a la vista). Los paneles (components/bi/)
 * pasan a Card/Section e Input/Select/Button del kit.
 */
import PageShell from '../components/layout/PageShell'
import PageHeader from '../components/layout/PageHeader'
import { Brain, Bell, ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import BiForecastingPanel from '../components/bi/BiForecastingPanel'
import BiAnomalyPanel from '../components/bi/BiAnomalyPanel'
import BiConditionalDeliveryPanel from '../components/bi/BiConditionalDeliveryPanel'
import { useAppT } from '../i18n/AppLangContext'
import './PredictionsPage.css'

export default function PredictionsPage() {
  const t = useAppT()

  return (
    <PageShell>
      <PageHeader
        icon={<Brain size={18} />}
        title={t('nav.predictions')}
        subtitle={t('predictions_page.subtitle')}
        showListExport={false}
      />

      <div className="u-stack-20">
        <BiForecastingPanel />
        <BiAnomalyPanel />
        <BiConditionalDeliveryPanel />

        <div className="ds-card pred-nota">
          <Bell size={16} className="pred-nota__icono" aria-hidden />
          <span className="pred-nota__texto">{t('predictions_page.alerts_hint')}</span>
          <Link to="/alerts" className="pred-enlace">
            {t('predictions_page.ir_a_alertas')} <ArrowRight size={13} aria-hidden />
          </Link>
        </div>
      </div>
    </PageShell>
  )
}
