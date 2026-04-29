/**
 * BiForecastingPanel.jsx — BI Forecasting panel (time-series predictions).
 * Connects to /api/v1/bi/forecast/* endpoints.
 */
import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Legend,
} from 'recharts'

const METHODS = ['linear', 'holt', 'prophet']
const DEFAULT_PERIODS = 6

export default function BiForecastingPanel() {
  const t = useAppT()
  const { dark, tokens } = useChartTheme()
  const [metric, setMetric] = useState('revenue')
  const [method, setMethod] = useState('linear')
  const [periods, setPeriods] = useState(DEFAULT_PERIODS)
  const [forecastData, setForecastData] = useState(null)

  const { data: metricsData } = useQuery({
    queryKey: ['bi-forecast-metrics'],
    queryFn: () => api.get('/bi/forecast/metrics').then(r => r.data),
  })

  const forecastMutation = useMutation({
    mutationFn: (payload) => api.post('/bi/forecast', payload).then(r => r.data),
    onSuccess: (data) => setForecastData(data),
  })

  const handleForecast = () => {
    forecastMutation.mutate({ metric, method, periods })
  }

  const chartData = forecastData?.forecast?.map((val, i) => ({
    period: `+${i + 1}`,
    value: typeof val === 'object' ? val.value : val,
    lower: typeof val === 'object' ? val.lower : undefined,
    upper: typeof val === 'object' ? val.upper : undefined,
  })) ?? []

  return (
    <div className={`rounded-xl border p-6 ${dark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`}>
      <h2 className="text-lg font-bold mb-4">{t('bi.forecasting.title', 'Forecasting BI')}</h2>

      {/* Controls */}
      <div className="flex flex-wrap gap-4 mb-6">
        <div>
          <label className="block text-xs font-medium mb-1">{t('bi.forecasting.metric', 'Métrica')}</label>
          <select
            value={metric}
            onChange={e => setMetric(e.target.value)}
            className={`rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
          >
            {(metricsData?.metrics ?? ['revenue', 'tickets', 'utilization', 'hours']).map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium mb-1">{t('bi.forecasting.method', 'Método')}</label>
          <select
            value={method}
            onChange={e => setMethod(e.target.value)}
            className={`rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
          >
            {METHODS.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium mb-1">{t('bi.forecasting.periods', 'Períodos')}</label>
          <input
            type="number"
            min={1}
            max={24}
            value={periods}
            onChange={e => setPeriods(Number(e.target.value))}
            className={`rounded border px-3 py-1.5 text-sm w-20 ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
          />
        </div>

        <div className="flex items-end">
          <button
            onClick={handleForecast}
            disabled={forecastMutation.isPending}
            className="px-4 py-1.5 rounded bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {forecastMutation.isPending ? '...' : t('bi.forecasting.run', 'Calcular forecast')}
          </button>
        </div>
      </div>

      {/* Chart */}
      {chartData.length > 0 && (
        <div>
          <p className="text-xs text-gray-500 mb-2">
            {t('bi.forecasting.result_label', 'Forecast')} — {metric} / {method}
            {forecastData?.mape != null && <span className="ml-2 text-yellow-500">MAPE: {Number(forecastData.mape).toFixed(1)}%</span>}
          </p>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke={dark ? '#374151' : '#e5e7eb'} />
              <XAxis dataKey="period" tick={{ fill: dark ? '#9ca3af' : '#6b7280', fontSize: 11 }} />
              <YAxis tick={{ fill: dark ? '#9ca3af' : '#6b7280', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: dark ? '#1f2937' : '#fff', border: '1px solid #374151', borderRadius: 8 }}
              />
              <Legend />
              <Line type="monotone" dataKey="value" stroke={tokens?.primary ?? '#3b82f6'} strokeWidth={2} dot={false} name={metric} />
              {chartData[0]?.lower != null && (
                <Line type="monotone" dataKey="lower" stroke="#94a3b8" strokeWidth={1} strokeDasharray="4 2" name="lower" />
              )}
              {chartData[0]?.upper != null && (
                <Line type="monotone" dataKey="upper" stroke="#94a3b8" strokeWidth={1} strokeDasharray="4 2" name="upper" />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {forecastMutation.isError && (
        <p className="text-red-500 text-sm mt-2">{t('bi.forecasting.error', 'Error al calcular forecast')}</p>
      )}
    </div>
  )
}
