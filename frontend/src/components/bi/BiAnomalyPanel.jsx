/**
 * BiAnomalyPanel.jsx — BI Anomaly Detection + Churn Prediction panel.
 * Connects to /api/v1/bi/anomaly/* and /api/v1/bi/churn/* endpoints.
 */
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'

const RISK_COLORS = { low: 'text-green-500', medium: 'text-yellow-500', high: 'text-red-500', critical: 'text-red-700' }

export default function BiAnomalyPanel() {
  const t = useAppT()
  const { dark } = useChartTheme()

  // Anomaly detection state
  const [anomalyMetric, setAnomalyMetric] = useState('revenue')
  const [anomalyResult, setAnomalyResult] = useState(null)

  // Churn prediction state
  const [churnClientId, setChurnClientId] = useState('')
  const [churnFeatures, setChurnFeatures] = useState({
    monthly_revenue: 5000,
    support_tickets_last_90d: 3,
    nps_score: 7,
    contract_months_remaining: 6,
    logins_last_30d: 10,
    open_invoices: 1,
  })
  const [churnResult, setChurnResult] = useState(null)

  const { data: infoData } = useQuery({
    queryKey: ['bi-anomaly-info'],
    queryFn: () => api.get('/bi/anomaly/info').then(r => r.data),
  })

  const anomalyMutation = useMutation({
    mutationFn: (payload) => api.post('/bi/anomaly/detect', payload).then(r => r.data),
    onSuccess: setAnomalyResult,
  })

  const churnMutation = useMutation({
    mutationFn: (payload) => api.post('/bi/churn/predict', payload).then(r => r.data),
    onSuccess: setChurnResult,
  })

  return (
    <div className="space-y-6">
      {/* Info banner */}
      {infoData && (
        <div className={`text-xs px-3 py-2 rounded ${dark ? 'bg-gray-800 text-gray-400' : 'bg-gray-100 text-gray-500'}`}>
          IsolationForest: {infoData.sklearn_available ? '✅' : '⚠️ fallback'} &nbsp;|&nbsp;
          LightGBM: {infoData.lgbm_available ? '✅' : '⚠️ fallback'}
        </div>
      )}

      {/* Anomaly Detection */}
      <div className={`rounded-xl border p-6 ${dark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`}>
        <h3 className="font-bold text-base mb-4">{t('bi.anomaly.title', 'Detección de Anomalías')}</h3>
        <div className="flex flex-wrap gap-3 mb-4">
          <select
            value={anomalyMetric}
            onChange={e => setAnomalyMetric(e.target.value)}
            className={`rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
          >
            {['revenue', 'tickets', 'utilization', 'hours', 'response_time'].map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <button
            onClick={() => anomalyMutation.mutate({ metric: anomalyMetric })}
            disabled={anomalyMutation.isPending}
            className="px-4 py-1.5 rounded bg-orange-600 text-white text-sm hover:bg-orange-700 disabled:opacity-50"
          >
            {anomalyMutation.isPending ? '...' : t('bi.anomaly.detect', 'Detectar')}
          </button>
        </div>

        {anomalyResult && (
          <div>
            <p className="text-sm mb-2">
              {t('bi.anomaly.found', 'Anomalías encontradas')}: <strong className="text-orange-500">{anomalyResult.anomaly_count ?? anomalyResult.anomalies?.length ?? 0}</strong>
              {' '}/ {anomalyResult.total_points} {t('bi.anomaly.points', 'puntos')}
            </p>
            {anomalyResult.anomalies?.slice(0, 5).map((a, i) => (
              <div key={i} className={`flex items-center gap-2 py-1 text-xs ${dark ? 'text-gray-300' : 'text-gray-600'}`}>
                <span className="text-orange-400">⚠</span>
                <span>{a.period ?? `punto ${a.index ?? i}`}: {a.value?.toFixed?.(2) ?? a.value}</span>
                {a.score != null && <span className="text-gray-400">score: {a.score.toFixed(3)}</span>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Churn Prediction */}
      <div className={`rounded-xl border p-6 ${dark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`}>
        <h3 className="font-bold text-base mb-4">{t('bi.churn.title', 'Predicción de Churn')}</h3>
        <div className="flex flex-wrap gap-3 mb-4">
          <input
            type="text"
            placeholder="client-id"
            value={churnClientId}
            onChange={e => setChurnClientId(e.target.value)}
            className={`rounded border px-3 py-1.5 text-sm w-36 ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
          />
          <button
            onClick={() => churnMutation.mutate({ client_id: churnClientId || 'demo-client', features: churnFeatures })}
            disabled={churnMutation.isPending}
            className="px-4 py-1.5 rounded bg-red-600 text-white text-sm hover:bg-red-700 disabled:opacity-50"
          >
            {churnMutation.isPending ? '...' : t('bi.churn.predict', 'Predecir churn')}
          </button>
        </div>

        {/* Feature inputs */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-4">
          {Object.entries(churnFeatures).map(([k, v]) => (
            <div key={k}>
              <label className="block text-xs mb-0.5">{k.replace(/_/g, ' ')}</label>
              <input
                type="number"
                value={v}
                onChange={e => setChurnFeatures(f => ({ ...f, [k]: Number(e.target.value) }))}
                className={`rounded border px-2 py-1 text-xs w-full ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
              />
            </div>
          ))}
        </div>

        {churnResult && (
          <div className={`rounded-lg px-4 py-3 ${dark ? 'bg-gray-800' : 'bg-gray-50'}`}>
            <p className="font-medium mb-1">
              {t('bi.churn.probability', 'Probabilidad de churn')}:{' '}
              <strong>{(churnResult.churn_probability * 100).toFixed(1)}%</strong>
            </p>
            <p className={`text-sm font-semibold ${RISK_COLORS[churnResult.risk_level] ?? 'text-gray-500'}`}>
              {t('bi.churn.risk', 'Riesgo')}: {churnResult.risk_level?.toUpperCase()}
            </p>
            {churnResult.top_factors?.length > 0 && (
              <ul className="mt-2 text-xs space-y-0.5">
                {churnResult.top_factors.slice(0, 3).map((f, i) => (
                  <li key={i} className="text-gray-500">→ {typeof f === 'string' ? f : `${f.feature}: ${f.importance?.toFixed(2)}`}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
