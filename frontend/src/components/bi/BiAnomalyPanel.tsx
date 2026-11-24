/**
 * BiAnomalyPanel — detección de anomalías y riesgo de abandono de clientes
 * (/predictions). Conecta con /api/v1/bi/anomaly/* y /api/v1/bi/churn/*.
 *
 * 16-11-2026: pasada de diseño. Antes: banda con el nombre interno de los modelos y
 * emojis de marca, botones naranja y rojo (rojo = destruir) para acciones normales, un
 * campo libre «client-id», etiquetas con el nombre interno del modelo
 * («tickets last 30d») y el nivel de riesgo en inglés y mayúsculas. Ahora:
 * tarjetas, campos y botones del kit, selector de cliente, etiquetas y
 * factores traducidos y el estado del modelo con StatusBadge.
 */
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { biAnomalyApi } from '../../services/api'
import type { AbandonoDeClienteBi, DeteccionDeAnomaliasBi, NivelDeAbandono } from '../../services/api/tipos-bi'
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaMetricaBi } from '../../i18n/catalogoMetricas'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { localeActivo } from '../../utils/helpers'
import { AlertTriangle, Calculator, Search, TrendingDown } from 'lucide-react'
import { Button, Card, ClientSelect, Input, Section, Select } from '../ui'
import StatusBadge from '../ui/StatusBadge'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import './BiAnomalyPanel.css'

const RIESGO: Record<NivelDeAbandono, StatusBadgeKind> = {
  low:    'success',
  medium: 'warning',
  high:   'danger',
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
  const fmtMoneda = useFormatoMoneda()
  const idCliente = 'bianpa-cliente'

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

  const factor = (k: string) => etiquetaCodigo(t, 'prediccion_bi.factor', k, k.replace(/_/g, ' '))
  const num = (v: number, dec: number) => v.toLocaleString(localeActivo(), { minimumFractionDigits: dec, maximumFractionDigits: dec })

  const estadoModelo = (avanzado: boolean | undefined) => (
    <StatusBadge kind={avanzado ? 'success' : 'neutral'} dot caps={false}>
      {avanzado ? t('prediccion_bi.modelo_avanzado') : t('prediccion_bi.modelo_basico')}
    </StatusBadge>
  )

  return (
    <div className="u-stack-20">
      {/* Anomaly Detection */}
      <Card>
        <Section
          title={<span className="bi-titulo"><AlertTriangle size={16} aria-hidden />{t('prediccion_bi.anomalias_titulo')}</span>}
          subtitle={t('prediccion_bi.anomalias_sub')}
          actions={infoData ? estadoModelo(infoData.sklearn_available) : undefined}
        >
          <div className="bianpa-controles">
            <Select label={t('prediccion_bi.metrica')} value={anomalyMetric} onChange={e => setAnomalyMetric(e.target.value)}
              options={ANOMALY_METRICS.map(m => ({ value: m, label: etiquetaMetricaBi(t, m, m, fmtMoneda.simbolo) }))} />
            <Button icon={<Search size={14} />} onClick={() => anomalyMutation.mutate({ metric: anomalyMetric })} loading={anomalyMutation.isPending}>
              {anomalyMutation.isPending ? t('prediccion_bi.analizando') : t('prediccion_bi.detectar')}
            </Button>
          </div>

          {anomalyResult && (
            <div className="u-stack-8">
              <p className="bi-nota">
                {t('prediccion_bi.anomalias_encontradas', { n: anomalyResult.anomaly_count, total: anomalyResult.total_points })}
              </p>
              {anomalyResult.anomalies.length === 0 ? (
                <p className="bi-nota">{t('prediccion_bi.sin_anomalias')}</p>
              ) : (
                <ul className="bianpa-lista">
                  {anomalyResult.anomalies.slice(0, 5).map((a, i) => (
                    <li key={i} className="bianpa-anomalia">
                      <AlertTriangle size={14} className="bianpa-icono-aviso" aria-hidden />
                      <span className="bianpa-anomalia__valor">{a.period ?? t('prediccion_bi.punto_n', { n: a.index + 1 })}: {num(a.value, 2)}</span>
                      <span className="bianpa-anomalia__puntos">{t('prediccion_bi.puntuacion', { v: num(a.score, 3) })}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {anomalyMutation.isError && <p className="bi-error" role="alert">{t('prediccion_bi.error_anomalias')}</p>}
        </Section>
      </Card>

      {/* Churn Prediction */}
      <Card>
        <Section
          title={<span className="bi-titulo"><TrendingDown size={16} aria-hidden />{t('prediccion_bi.abandono_titulo')}</span>}
          subtitle={t('prediccion_bi.abandono_sub')}
          actions={infoData ? estadoModelo(infoData.lgbm_available) : undefined}
        >
          <div className="bianpa-controles">
            <ClientSelect label={t('prediccion_bi.cliente')} id={idCliente} value={churnClientId} onChange={id => setChurnClientId(id)} />
            <Button icon={<Calculator size={14} />}
              onClick={() => churnMutation.mutate({ client_id: churnClientId || 'demo-client', features: churnFeatures })}
              loading={churnMutation.isPending}>
              {churnMutation.isPending ? t('prediccion_bi.calculando') : t('prediccion_bi.calcular_riesgo')}
            </Button>
          </div>

          <div className="bianpa-factores">
            {Object.entries(churnFeatures).map(([k, v]) => (
              <Input key={k} label={factor(k)} type="number" value={v}
                onChange={e => setChurnFeatures(f => ({ ...f, [k]: Number(e.target.value) }))} />
            ))}
          </div>

          {churnResult && (
            <div className="bianpa-resultado">
              <div className="bianpa-resultado__fila">
                <span className="bi-nota">{t('prediccion_bi.probabilidad')}</span>
                <strong className="bianpa-resultado__cifra">{num(churnResult.churn_probability * 100, 1)}%</strong>
                <StatusBadge kind={RIESGO[churnResult.risk_level] ?? 'neutral'} caps={false}>
                  {t('prediccion_bi.riesgo', { nivel: etiquetaCodigo(t, 'prediccion_bi.nivel', churnResult.risk_level) })}
                </StatusBadge>
              </div>
              {churnResult.top_factors.length > 0 && (
                <div className="u-stack-6">
                  <span className="ds-eyebrow">{t('prediccion_bi.factores')}</span>
                  <ul className="bianpa-lista">
                    {churnResult.top_factors.slice(0, 3).map((f, i) => (
                      <li key={i} className="bianpa-factor">{factor(f)}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
          {churnMutation.isError && <p className="bi-error" role="alert">{t('prediccion_bi.error_abandono')}</p>}
        </Section>
      </Card>
    </div>
  )
}
