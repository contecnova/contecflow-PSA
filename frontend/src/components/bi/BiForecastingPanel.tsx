/**
 * BiForecastingPanel — previsión de series temporales (/predictions).
 * Conecta con /api/v1/bi/forecast/*.
 *
 * 16-11-2026: pasada de diseño. Tarjeta, campos y botón del kit (antes estilos
 * en línea con campos de fondo gris); métodos con nombre traducido (antes
 * `linear_trend` tal cual) y textos en los tres idiomas (antes, valores por
 * defecto en castellano de claves que no existían).
 */
import { useState } from 'react'
import { tooltipDelTema } from '../../constants/estilosGrafico'
import { useQuery, useMutation } from '@tanstack/react-query'
import { biForecastingApi } from '../../services/api'
import type { PrevisionBi } from '../../services/api/tipos-bi'
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaMetricaBi } from '../../i18n/catalogoMetricas'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { useChartTheme } from '../../charts/useChartTheme'
import { Play, TrendingUp } from 'lucide-react'
import { Button, Card, Input, Section, Select } from '../ui'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Legend,
} from 'recharts'
import './BiForecastingPanel.css'

// Las que acepta el servicio (`SUPPORTED_METRICS` / `SUPPORTED_METHODS`), por si
// la lista del servidor aún no ha llegado.
const METRICAS_POR_DEFECTO = ['revenue', 'margin', 'tickets_open', 'utilization', 'tasks_overdue', 'budget_used_pct', 'active_projects']
const METODOS_POR_DEFECTO = ['linear_trend', 'holt', 'arima', 'prophet']

export default function BiForecastingPanel() {
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

  const nombreMetrica = (m: string) => etiquetaMetricaBi(t, m, m, fmtMoneda.simbolo)
  const nombreMetodo = (m: string) => etiquetaCodigo(t, 'prediccion_bi.metodo', m)

  // Listas paralelas: una posición por periodo en `forecast`, `lower_bound` y `upper_bound`.
  const chartData = forecastData?.forecast.map((value, i) => ({
    period: `+${i + 1}`,
    value,
    lower:  forecastData.lower_bound[i],
    upper:  forecastData.upper_bound[i],
  })) ?? []

  return (
    <Card>
      <Section
        title={<span className="bi-titulo"><TrendingUp size={16} aria-hidden />{t('prediccion_bi.prevision_titulo')}</span>}
        subtitle={t('biforecasting.predicciones_de_series_temporales')}
      >
        <div className="bifopa-controles">
          <Select label={t('prediccion_bi.metrica')} value={metric} onChange={e => setMetric(e.target.value)}
            options={(metricsData?.metrics ?? METRICAS_POR_DEFECTO).map(m => ({ value: m, label: nombreMetrica(m) }))} />
          <Select label={t('prediccion_bi.metodo_campo')} value={method} onChange={e => setMethod(e.target.value)}
            options={(metricsData?.methods ?? METODOS_POR_DEFECTO).map(m => ({ value: m, label: nombreMetodo(m) }))} />
          <Input label={t('prediccion_bi.periodos')} type="number" value={periods}
            onChange={e => setPeriods(Math.min(24, Math.max(1, Number(e.target.value) || 1)))} />
          <Button icon={<Play size={14} />} onClick={() => forecastMutation.mutate({ metric, method, periods })} loading={forecastMutation.isPending}>
            {forecastMutation.isPending ? t('prediccion_bi.calculando') : t('prediccion_bi.calcular')}
          </Button>
        </div>

        {chartData.length > 0 && (
          <div className="u-stack-8">
            <p className="bi-nota">
              {t('prediccion_bi.resultado', { metrica: nombreMetrica(metric), metodo: nombreMetodo(method) })}
            </p>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="period" tick={{ fill: tokens.textColor, fontSize: "var(--text-xs)" }} />
                <YAxis tick={{ fill: tokens.textColor, fontSize: "var(--text-xs)" }} />
                <Tooltip contentStyle={tooltipDelTema(tokens)} />
                <Legend />
                <Line type="monotone" dataKey="value" stroke={tokens?.primary ?? 'var(--accent)'} strokeWidth={2} dot={false} name={t('prediccion_bi.serie_prevision')} />
                {chartData[0]?.lower != null && (
                  <Line type="monotone" dataKey="lower" stroke="var(--text-3)" strokeWidth={1} strokeDasharray="4 2" name={t('prediccion_bi.serie_minimo')} />
                )}
                {chartData[0]?.upper != null && (
                  <Line type="monotone" dataKey="upper" stroke="var(--text-3)" strokeWidth={1} strokeDasharray="4 2" name={t('prediccion_bi.serie_maximo')} />
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {forecastMutation.isError && (
          <p className="bi-error" role="alert">{t('prediccion_bi.error_prevision')}</p>
        )}
      </Section>
    </Card>
  )
}
