/**
 * BiForecastingPanel.jsx — BI Forecasting panel (time-series predictions).
 * Connects to /api/v1/bi/forecast/* endpoints.
 */
import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { biForecastingApi } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import { TrendingUp } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Legend,
} from 'recharts'

const METHODS = ['linear', 'holt', 'prophet']

const S = {
  card:   { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14, padding: '20px 24px' },
  input:  { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", fontFamily: 'inherit', outline: 'none', width: '100%', boxSizing: 'border-box' },
  select: { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", fontFamily: 'inherit', outline: 'none' },
  label:  { fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 },
  btn:    { padding: '7px 16px', borderRadius: 8, background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit' },
}

export default function BiForecastingPanel() {
  const t              = useAppT()
  const { tokens }     = useChartTheme()
  const [metric, setMetric]   = useState('revenue')
  const [method, setMethod]   = useState('linear')
  const [periods, setPeriods] = useState(6)
  const [forecastData, setForecastData] = useState(null)

  const { data: metricsData } = useQuery({
    queryKey: ['bi-forecast-metrics'],
    queryFn:  () => biForecastingApi.listMetrics().then(r => r.data),
  })

  const forecastMutation = useMutation({
    mutationFn: (payload) => biForecastingApi.run(payload).then(r => r.data),
    onSuccess:  (data) => setForecastData(data),
  })

  const chartData = forecastData?.forecast?.map((val, i) => ({
    period: `+${i + 1}`,
    value:  typeof val === 'object' ? val.value : val,
    lower:  typeof val === 'object' ? val.lower  : undefined,
    upper:  typeof val === 'object' ? val.upper  : undefined,
  })) ?? []

  return (
    <div style={S.card}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--accent-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)' }}>
          <TrendingUp size={16} />
        </div>
        <div>
          <h3 style={{ margin: 0, fontSize: "var(--text-md-em)", fontWeight: 700, color: 'var(--text-1)' }}>
            {t('bi.forecasting.title', 'Forecasting BI')}
          </h3>
          <p style={{ margin: 0, fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>Predicciones de series temporales</p>
        </div>
      </div>

      {/* Controls */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginBottom: 24 }}>
        <div>
          <label style={S.label}>{t('bi.forecasting.metric', 'Métrica')}</label>
          <select value={metric} onChange={e => setMetric(e.target.value)} style={S.select}>
            {(metricsData?.metrics ?? ['revenue', 'tickets', 'utilization', 'hours']).map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        <div>
          <label style={S.label}>{t('bi.forecasting.method', 'Método')}</label>
          <select value={method} onChange={e => setMethod(e.target.value)} style={S.select}>
            {METHODS.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        <div>
          <label style={S.label}>{t('bi.forecasting.periods', 'Períodos')}</label>
          <input
            type="number" min={1} max={24}
            value={periods}
            onChange={e => setPeriods(Number(e.target.value))}
            style={{ ...S.input, width: 80 }}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'flex-end' }}>
          <button
            onClick={() => forecastMutation.mutate({ metric, method, periods })}
            disabled={forecastMutation.isPending}
            style={{ ...S.btn, opacity: forecastMutation.isPending ? 0.5 : 1 }}
          >
            {forecastMutation.isPending ? '...' : t('bi.forecasting.run', 'Calcular forecast')}
          </button>
        </div>
      </div>

      {/* Chart */}
      {chartData.length > 0 && (
        <div>
          <p style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 8 }}>
            {t('bi.forecasting.result_label', 'Forecast')} — {metric} / {method}
            {forecastData?.mape != null && (
              <span style={{ marginLeft: 8, color: 'var(--warning)' }}>MAPE: {Number(forecastData.mape).toFixed(1)}%</span>
            )}
          </p>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
              <XAxis dataKey="period" tick={{ fill: tokens.textColor, fontSize: "var(--text-xs)" }} />
              <YAxis tick={{ fill: tokens.textColor, fontSize: "var(--text-xs)" }} />
              <Tooltip contentStyle={{ background: tokens.tooltipBg, border: 'none', borderRadius: 8, color: 'var(--text-1)' }} />
              <Legend />
              <Line type="monotone" dataKey="value" stroke={tokens?.primary ?? 'var(--accent)'} strokeWidth={2} dot={false} name={metric} />
              {chartData[0]?.lower != null && (
                <Line type="monotone" dataKey="lower" stroke="var(--text-3)" strokeWidth={1} strokeDasharray="4 2" name="lower" />
              )}
              {chartData[0]?.upper != null && (
                <Line type="monotone" dataKey="upper" stroke="var(--text-3)" strokeWidth={1} strokeDasharray="4 2" name="upper" />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {forecastMutation.isError && (
        <p style={{ fontSize: "var(--text-sm)", color: 'var(--danger)', marginTop: 8 }}>
          {t('bi.forecasting.error', 'Error al calcular forecast')}
        </p>
      )}
    </div>
  )
}
