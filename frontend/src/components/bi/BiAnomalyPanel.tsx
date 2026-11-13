/**
 * BiAnomalyPanel.jsx — BI Anomaly Detection + Churn Prediction panel.
 * Connects to /api/v1/bi/anomaly/* and /api/v1/bi/churn/* endpoints.
 */
import React, { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { biAnomalyApi } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { AlertTriangle, TrendingDown } from 'lucide-react'

const RISK_COLORS: Record<string, string> = {
  low:      'var(--success)',
  medium:   'var(--warning)',
  high:     'var(--danger)',
  critical: 'var(--danger)',
}

// TODO type: biAnomalyApi responses — needs shared types
interface AnomalyPoint {
  period?: string
  index?: number
  value?: number
  score?: number
}

interface AnomalyResult {
  anomaly_count?: number
  total_points?: number
  anomalies?: AnomalyPoint[]
}

interface ChurnFactor {
  feature: string
  importance?: number
}

interface ChurnResult {
  churn_probability: number
  risk_level?: string
  top_factors?: Array<ChurnFactor | string>
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

const S: Record<string, React.CSSProperties> = {
  card:   { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-lg)', padding: '20px 24px' },
  input:  { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", fontFamily: 'inherit', outline: 'none', width: '100%', boxSizing: 'border-box' },
  select: { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", fontFamily: 'inherit', outline: 'none' },
  label:  { fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 },
  btnOrange: { padding: '7px 16px', borderRadius: 8, background: 'var(--orange)', color: 'var(--on-accent-light)', border: 'none', cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit' },
  btnRed:    { padding: '7px 16px', borderRadius: 8, background: 'var(--danger)', color: 'var(--on-accent-light)', border: 'none', cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit' },
}

export default function BiAnomalyPanel() {
  const t = useAppT()

  const [anomalyMetric, setAnomalyMetric] = useState<string>('revenue')
  const [anomalyResult, setAnomalyResult] = useState<AnomalyResult | null>(null)

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
  const [churnResult, setChurnResult] = useState<ChurnResult | null>(null)

  // TODO type: biAnomalyApi.getInfo response
  const { data: infoData } = useQuery<{ sklearn_available?: boolean; lgbm_available?: boolean }>({
    queryKey: ['bi-anomaly-info'],
    queryFn: () => biAnomalyApi.getInfo().then(r => r.data),
  })

  const anomalyMutation = useMutation<AnomalyResult, unknown, { metric: string }>({
    mutationFn: (payload) => biAnomalyApi.detect(payload).then(r => r.data),
    onSuccess: setAnomalyResult,
  })

  const churnMutation = useMutation<ChurnResult, unknown, { client_id: string; features: ChurnFeatures }>({
    mutationFn: (payload) => biAnomalyApi.churnPredict(payload).then(r => r.data),
    onSuccess: setChurnResult,
  })

  return (
    <div className="u-stack-20">
      {/* Info banner */}
      {infoData && (
        <div style={{ fontSize: "var(--text-xs)", padding: '8px 12px', borderRadius: 8, background: 'var(--surface-3)', color: 'var(--text-3)', border: '1px solid var(--surface-4)' }}>
          IsolationForest: {infoData.sklearn_available ? '✅' : '⚠️ fallback'} &nbsp;|&nbsp;
          LightGBM: {infoData.lgbm_available ? '✅' : '⚠️ fallback'}
        </div>
      )}

      {/* Anomaly Detection */}
      <div style={S.card}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(234,88,12,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--orange)' }}>
            <AlertTriangle size={16} />
          </div>
          <h3 style={{ margin: 0, fontSize: "var(--text-md-em)", fontWeight: 700, color: 'var(--text-1)' }}>
            {t('bi.anomaly.title', 'Detección de Anomalías')}
          </h3>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
          <select value={anomalyMetric} onChange={e => setAnomalyMetric(e.target.value)} style={S.select}>
            {ANOMALY_METRICS.map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <button
            onClick={() => anomalyMutation.mutate({ metric: anomalyMetric })}
            disabled={anomalyMutation.isPending}
            style={{ ...S.btnOrange, opacity: anomalyMutation.isPending ? 0.5 : 1 }}
          >
            {anomalyMutation.isPending ? '...' : t('bi.anomaly.detect', 'Detectar')}
          </button>
        </div>

        {anomalyResult && (
          <div>
            <p style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 8 }}>
              {t('bi.anomaly.found', 'Anomalías encontradas')}:{' '}
              <strong style={{ color: 'var(--orange)' }}>{anomalyResult.anomaly_count ?? anomalyResult.anomalies?.length ?? 0}</strong>
              {' '}/ {anomalyResult.total_points} {t('bi.anomaly.points', 'puntos')}
            </p>
            {anomalyResult.anomalies?.slice(0, 5).map((a, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0', fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
                <span style={{ color: 'var(--orange)' }}>⚠</span>
                <span>{a.period ?? `punto ${a.index ?? i}`}: {a.value?.toFixed?.(2) ?? a.value}</span>
                {a.score != null && <span className="u-text3">score: {a.score.toFixed(3)}</span>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Churn Prediction */}
      <div style={S.card}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(239,68,68,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--danger)' }}>
            <TrendingDown size={16} />
          </div>
          <h3 style={{ margin: 0, fontSize: "var(--text-md-em)", fontWeight: 700, color: 'var(--text-1)' }}>
            {t('bi.churn.title', 'Predicción de Churn')}
          </h3>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
          <input aria-label="client-id"
            type="text"
            placeholder="client-id"
            value={churnClientId}
            onChange={e => setChurnClientId(e.target.value)}
            style={{ ...S.input, width: 144 }}
          />
          <button
            onClick={() => churnMutation.mutate({ client_id: churnClientId || 'demo-client', features: churnFeatures })}
            disabled={churnMutation.isPending}
            style={{ ...S.btnRed, opacity: churnMutation.isPending ? 0.5 : 1 }}
          >
            {churnMutation.isPending ? '...' : t('bi.churn.predict', 'Predecir churn')}
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 10, marginBottom: 16 }}>
          {Object.entries(churnFeatures).map(([k, v]) => (
            <div key={k}>
              <label style={S.label}>{k.replace(/_/g, ' ')}</label>
              <input
                type="number"
                value={v}
                onChange={e => setChurnFeatures(f => ({ ...f, [k]: Number(e.target.value) }))}
                style={S.input}
              />
            </div>
          ))}
        </div>

        {churnResult && (
          <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: '12px 16px' }}>
            {(() => {
              const riskKey = churnResult.risk_level ?? 'low'
              const factors = churnResult.top_factors ?? []
              return (
                <>
            <p style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', marginBottom: 6 }}>
              {t('bi.churn.probability', 'Probabilidad de churn')}:{' '}
              <strong>{(churnResult.churn_probability * 100).toFixed(1)}%</strong>
            </p>
            <p style={{ fontSize: "var(--text-base)", fontWeight: 700, color: RISK_COLORS[riskKey] ?? 'var(--text-3)', marginBottom: factors.length ? 8 : 0 }}>
              {t('bi.churn.risk', 'Riesgo')}: {(churnResult.risk_level ?? 'low').toUpperCase()}
            </p>
            {factors.length > 0 && (
              <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                {factors.slice(0, 3).map((f, i) => (
                  <li key={i} style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', padding: '2px 0' }}>
                    → {typeof f === 'string' ? f : `${f.feature}: ${f.importance?.toFixed(2)}`}
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
