/**
 * BiAnomalyPanel.jsx — BI Anomaly Detection + Churn Prediction panel.
 * Connects to /api/v1/bi/anomaly/* and /api/v1/bi/churn/* endpoints.
 */
import { type CSSProperties, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { biAnomalyApi } from '../../services/api'
import type { AbandonoDeClienteBi, DeteccionDeAnomaliasBi, NivelDeAbandono } from '../../services/api/tipos-bi'
import { useAppT } from '../../i18n/AppLangContext'
import { AlertTriangle, TrendingDown } from 'lucide-react'
import './BiAnomalyPanel.css'

const RISK_COLORS: Record<NivelDeAbandono, string> = {
  low:      'var(--success)',
  medium:   'var(--warning)',
  high:     'var(--danger)',
}

// Los nombres que usa el modelo (`CHURN_FEATURES` en bi_anomaly_service).
interface ChurnFeatures {
  tickets_last_30d: number
  response_time_avg_h: number
  nps_score: number
  contract_renewal_days: number
  support_escalations: number
  last_login_days_ago: number
  active_projects: number
  [k: string]: number
}

// Claves con serie en `_fetch_metric_series`; una desconocida devuelve ceros.
const ANOMALY_METRICS = ['revenue', 'tickets_created', 'utilization', 'hours_logged', 'first_response_time_avg']


export default function BiAnomalyPanel() {
  const t = useAppT()

  const [anomalyMetric, setAnomalyMetric] = useState<string>('revenue')
  const [anomalyResult, setAnomalyResult] = useState<DeteccionDeAnomaliasBi | null>(null)

  const [churnClientId, setChurnClientId] = useState<string>('')
  const [churnFeatures, setChurnFeatures] = useState<ChurnFeatures>({
    tickets_last_30d: 3,
    response_time_avg_h: 8,
    nps_score: 7,
    contract_renewal_days: 180,
    support_escalations: 0,
    last_login_days_ago: 5,
    active_projects: 1,
  })
  const [churnResult, setChurnResult] = useState<AbandonoDeClienteBi | null>(null)

  const { data: infoData } = useQuery({
    queryKey: ['bi-anomaly-info'],
    queryFn: () => biAnomalyApi.getInfo().then(r => r.data),
  })

  const anomalyMutation = useMutation({
    mutationFn: (payload: { metric: string }) => biAnomalyApi.detect(payload).then(r => r.data),
    onSuccess: setAnomalyResult,
  })

  const churnMutation = useMutation({
    // Con `client_id` el servidor devuelve solo ese cliente; sin él, el lote (`clients`).
    mutationFn: (payload: { client_id: string; features: ChurnFeatures }) => biAnomalyApi.churnPredict(payload).then(r => ('clients' in r.data ? r.data.clients[0] : r.data)),
    onSuccess: setChurnResult,
  })

  return (
    <div className="u-stack-20">
      {/* Info banner */}
      {infoData && (
        <div className="bianpa-box-1">
          IsolationForest: {infoData.sklearn_available ? '✅' : '⚠️ fallback'} &nbsp;|&nbsp;
          LightGBM: {infoData.lgbm_available ? '✅' : '⚠️ fallback'}
        </div>
      )}

      {/* Anomaly Detection */}
      <div className="bi-anomaly-panel-e6">
        <div className="bianpa-row-1">
          <div className="bianomal-sx1">
            <AlertTriangle size={16} />
          </div>
          <h3 className="bianpa-box-2">
            {t('bi.anomaly.title', 'Detección de Anomalías')}
          </h3>
        </div>

        <div className="bianpa-row-2">
          <select value={anomalyMetric} onChange={e => setAnomalyMetric(e.target.value)} className="bi-anomaly-panel-e7">
            {ANOMALY_METRICS.map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <button className={`bianpa-btnorange ${anomalyMutation.isPending ? 'bi-anomaly-panel-m1' : 'bi-anomaly-panel-m2'}`}
            onClick={() => anomalyMutation.mutate({ metric: anomalyMetric })}
            disabled={anomalyMutation.isPending}
          >
            {anomalyMutation.isPending ? '...' : t('bi.anomaly.detect', 'Detectar')}
          </button>
        </div>

        {anomalyResult && (
          <div>
            <p className="bianpa-box-3">
              {t('bi.anomaly.found', 'Anomalías encontradas')}:{' '}
              <strong className="bianpa-txt-2">{anomalyResult.anomaly_count}</strong>
              {' '}/ {anomalyResult.total_points} {t('bi.anomaly.points', 'puntos')}
            </p>
            {anomalyResult.anomalies.slice(0, 5).map((a, i) => (
              <div key={i} className="bianpa-row-3">
                <span className="bianpa-txt-2">⚠</span>
                <span>{a.period ?? `punto ${a.index}`}: {a.value.toFixed(2)}</span>
                <span className="u-text3">score: {a.score.toFixed(3)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Churn Prediction */}
      <div className="bi-anomaly-panel-e6">
        <div className="bianpa-row-1">
          <div className="bianomal-sx2">
            <TrendingDown size={16} />
          </div>
          <h3 className="bianpa-box-2">
            {t('bi.churn.title', 'Predicción de Churn')}
          </h3>
        </div>

        <div className="bianpa-row-2">
          <input aria-label="client-id"
            type="text"
            placeholder="client-id"
            value={churnClientId}
            onChange={e => setChurnClientId(e.target.value)}
            className="bianpa-input"
          />
          <button className={`bianpa-btnred ${churnMutation.isPending ? 'bi-anomaly-panel-m1' : 'bi-anomaly-panel-m2'}`}
            onClick={() => churnMutation.mutate({ client_id: churnClientId || 'demo-client', features: churnFeatures })}
            disabled={churnMutation.isPending}
          >
            {churnMutation.isPending ? '...' : t('bi.churn.predict', 'Predecir churn')}
          </button>
        </div>

        <div className="bianpa-grid-1">
          {Object.entries(churnFeatures).map(([k, v]) => (
            <div key={k}>
              <label className="bi-anomaly-panel-e8">{k.replace(/_/g, ' ')}</label>
              <input
                type="number"
                aria-label={k.replace(/_/g, ' ')}
                value={v}
                onChange={e => setChurnFeatures(f => ({ ...f, [k]: Number(e.target.value) }))}
                className="bi-anomaly-panel-e9"
              />
            </div>
          ))}
        </div>

        {churnResult && (
          <div className="bianpa-box-4">
            {(() => {
              const riskKey = churnResult.risk_level
              const factors = churnResult.top_factors
              return (
                <>
            <p className="bianpa-box-5">
              {t('bi.churn.probability', 'Probabilidad de churn')}:{' '}
              <strong>{(churnResult.churn_probability * 100).toFixed(1)}%</strong>
            </p>
            <p className={`bianpa-txt-1 bi-anomaly-panel-e3 ${factors.length ? 'bi-anomaly-panel-m4' : 'bi-anomaly-panel-m5'}`} style={{ '--bi-anomaly-panel-color': RISK_COLORS[riskKey] } as CSSProperties}>
              {t('bi.churn.risk', 'Riesgo')}: {churnResult.risk_level.toUpperCase()}
            </p>
            {factors.length > 0 && (
              <ul className="bianpa-box-6">
                {factors.slice(0, 3).map((f, i) => (
                  <li key={i} className="bianpa-box-7">
                    → {f}
                  </li>
                ))}
              </ul>
            )}
                </>
              )
            })()}
          </div>
        )}
      </div>
    </div>
  )
}
