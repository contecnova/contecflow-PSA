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

export default function PredictionsPage() {
  const isMobile = useMediaQuery('(max-width: 900px)')

  return (
    <PageShell style={isMobile ? { paddingLeft: 14, paddingRight: 14 } : undefined}>
      <PageHeader
        icon={<Brain size={18} />}
        title="Predictions"
        subtitle="Forecasting con ML, detección de anomalías y entrega condicional"
      showListExport={false}
      />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <BiForecastingPanel />
        <BiAnomalyPanel />
        <BiConditionalDeliveryPanel />

        <div style={{
          background: 'var(--surface-2)', border: '1px dashed var(--surface-4)', borderRadius: 12,
          padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 10, fontSize: 'var(--text-sm)', color: 'var(--text-2)',
        }}>
          <Bell size={16} style={{ color: 'var(--accent)' }} />
          <span>
            Las reglas de <strong>Smart Alerts</strong> (alertas basadas en estas predicciones) se gestionan en{' '}
            <Link to="/alerts" style={{ color: 'var(--accent)', textDecoration: 'underline' }}>/alerts</Link>, pestaña <em>Inteligentes</em>.
          </span>
        </div>
      </div>
    </PageShell>
  )
}
