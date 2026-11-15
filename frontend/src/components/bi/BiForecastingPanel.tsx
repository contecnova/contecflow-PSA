/**
 * BiForecastingPanel.jsx — BI Forecasting panel (time-series predictions).
 * Connects to /api/v1/bi/forecast/* endpoints.
 */
import React, { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { biForecastingApi } from '../../services/api'
import type { PrevisionBi } from '../../services/api/tipos-bi'
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaMetricaBi } from '../../i18n/catalogoMetricas'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { useChartTheme } from '../../charts/useChartTheme'
import { TrendingUp } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Legend,
} from 'recharts'
import './BiForecastingPanel.css'

const S: Record<string, React.CSSProperties> = {
  card:   { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-lg)', padding: '20px 24px' },
  input:  { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", fontFamily: 'inherit', outline: 'none', width: '100%', boxSizing: 'border-box' },
  select: { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", fontFamily: 'inherit', outline: 'none' },
  label:  { fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 },
  btn:    { padding: '7px 16px', borderRadius: 8, background: 'var(--accent)', color: 'var(--on-accent)', border: 'none', cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit' },
}

export default function BiForecastingPanel() {
  const idCampo = React.useId()
  const t              = useAppT()
  const fmtMoneda      = useFormatoMoneda()
  const { tokens }     = useChartTheme()
  const [metric, setMetric]   = useState<string>('revenue')
  const [method, setMethod]   = useState<string>('linear_trend')
  const [periods, setPeriods] = useState<number>(6)
  const [forecastData, setForecastData] = useState<PrevisionBi | null>(null)

  const { data: metricsData } = useQuery({
    queryKey: ['bi-forecast-metrics'],
    queryFn:  () => biForecastingApi.getMetrics().then(r => r.data),
  })

  const forecastMutation = useMutation({
    mutationFn: (payload: { metric: string; method: string; periods: number }) => biForecastingApi.forecast(payload.metric, { method: payload.method, periods: payload.periods }).then(r => r.data),
    onSuccess:  (data) => setForecastData(data),
  })

  // Listas paralelas: una posición por periodo en `forecast`, `lower_bound` y `upper_bound`.
  const chartData = forecastData?.forecast.map((value, i) => ({
    period: `+${i + 1}`,
    value,
    lower:  forecastData.lower_bound[i],
    upper:  forecastData.upper_bound[i],
  })) ?? []

  return (
    <div style={S.card}>
      {/* Header */}
      <div className="bifopa-row-1">
        <div className="bifopa-row-2">
          <TrendingUp size={16} />
        </div>
        <div>
          <h3 className="bifopa-box-1">
            {t('bi.forecasting.title', 'Forecasting BI')}
          </h3>
          <p className="bifopa-box-2">{t('biforecasting.predicciones_de_series_temporales')}</p>
        </div>
      </div>

      {/* Controls */}
      <div className="bifopa-row-3">
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={S.label}>{t('bi.forecasting.metric', 'Métrica')}</label>
          <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={metric} onChange={e => setMetric(e.target.value)} style={S.select}>
            {(metricsData?.metrics ?? ['revenue', 'tickets', 'utilization', 'hours']).map(m => (
              <option key={m} value={m}>{etiquetaMetricaBi(t, m, m, fmtMoneda.simbolo)}</option>
            ))}
          </select>
        </div>

        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={S.label}>{t('bi.forecasting.method', 'Método')}</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={method} onChange={e => setMethod(e.target.value)} style={S.select}>
            {(metricsData?.methods ?? [method]).map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={S.label}>{t('bi.forecasting.periods', 'Períodos')}</label>
          <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`}
            type="number" min={1} max={24}
            value={periods}
            onChange={e => setPeriods(Number(e.target.value))}
            className="bifopa-input"
          />
        </div>

        <div className="bifopa-row-4">
          <button className="bifopa-btn"
            onClick={() => forecastMutation.mutate({ metric, method, periods })}
            disabled={forecastMutation.isPending}
            style={{ opacity: forecastMutation.isPending ? 0.5 : 1 }}
          >
            {forecastMutation.isPending ? '...' : t('bi.forecasting.run', 'Calcular forecast')}
          </button>
        </div>
      </div>

      {/* Chart */}
      {chartData.length > 0 && (
        <div>
          <p className="bifopa-box-3">
            {t('bi.forecasting.result_label', 'Forecast')} — {metric} / {method}
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
        <p className="bifopa-box-4">
          {t('bi.forecasting.error', 'Error al calcular forecast')}
        </p>
      )}
    </div>
  )
}
