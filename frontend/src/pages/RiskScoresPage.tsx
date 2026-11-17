/**
 * RiskScoresPage — Predicción de riesgo por proyecto
 * Motor basado en señales observables: schedule, budget, scope, recursos
 *
 * 16-11-2026: pasada de diseño. Título como el menú ("Riesgo del proyecto");
 * pestañas con Tabs (antes subrayadas y con emojis); KPIs con KpiCard (antes
 * fondo tintado y emojis de colores) y el filtro por nivel en un select de
 * la barra; "Recalcular todo" a la cabecera; niveles, recomendaciones y
 * cerrar con iconos lucide; vacíos con EmptyState e icono.
 */
import { useState, type CSSProperties, type ReactNode } from 'react'
import { extractErr, fmtDate, fmtDateTime, formateadorDeFecha } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { predictionsApi } from '../services/api'
import type { ModeloDePrediccion, RegistroDePrediccion, RiesgoDeLaCartera } from '../services/api/tipos-analitica'
import { Spinner, EmptyState, Button, KpiCard, Tabs, Select, Pulsable, IconButton } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AlertCircle, AlertOctagon, AlertTriangle, Brain, CheckCircle2, Lightbulb, RefreshCw, Search, ShieldAlert, ShieldCheck, X } from 'lucide-react'
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer, Tooltip } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'
import { PREDICTION_LOGS_LIMIT } from '../constants/pagination'
import './RiskScoresPage.css'

type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

type MlPortfolioRiskProject = RiesgoDeLaCartera['at_risk_projects'][number]
type MlPortfolioRiskData = RiesgoDeLaCartera
type MlModel = ModeloDePrediccion
type MlPredictionLog = RegistroDePrediccion

type RiskProject = {
  project_id: string | number
  project_name?: string
  project_code?: string
  level?: RiskLevel
  overall_score?: number
  schedule_risk?: number
  budget_risk?: number
  scope_risk?: number
  resource_risk?: number
  recommendation?: string
  delay_probability_pct?: number
  predicted_delay_weeks?: number
  computed_at?: string
}

type RiskSummary = Partial<Record<RiskLevel, number>>

type RiskScoresResponse = {
  projects?: RiskProject[]
  summary?: RiskSummary
}

type RiskDetail = {
  project_name?: string
  schedule_risk?: number
  budget_risk?: number
  scope_risk?: number
  resource_risk?: number
  recommendation?: string
  delay_probability_pct?: number
  predicted_delay_weeks?: number
  history?: Array<{ computed_at: string; overall_score: number; level: RiskLevel }>
}

type RadarDatum = {
  subject: string
  A: number
}

const LEVEL_ICON: Record<RiskLevel, ReactNode> = {
  low: <CheckCircle2 size={18} />,
  medium: <AlertCircle size={18} />,
  high: <AlertTriangle size={18} />,
  critical: <AlertOctagon size={18} />,
}

/** Umbral de color de una puntuación 0–100. */
const tono = (v: number) => v >= 75 ? 'danger' : v >= 50 ? 'warning' : 'success'
const anchura = (v: number) => ({ '--pct': `${Math.min(Math.max(v, 0), 100)}%` }) as CSSProperties

function ScoreBar({ value, label }: { value: number; label: string }) {
  const tn = tono(value)
  return (
    <div className="u-mb-10">
      <div className="rsc-scorebar__head">
        <span className="u-text2">{label}</span>
        <span className={`rsc-scorebar__value rsc-scorebar__value--${tn}`}>{Math.round(value)}%</span>
      </div>
      <div className="rsc-track rsc-track--lg" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value)}>
        <div className={`rsc-fill rsc-fill--${tn}`} style={anchura(value)} />
      </div>
    </div>
  )
}

function MLPredictionsTab() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const nivelMl = (l: RiskLevel) => t(`risk_scores_page.ml_nivel_${l}`)

  const { data: portfolio, isLoading: lPortfolio } = useQuery<MlPortfolioRiskData>({
    queryKey: ['ml-portfolio-risk'],
    queryFn: () => predictionsApi.portfolioRisk().then(r => r.data),
    retry: 1,
  })
  const { data: models = [], isLoading: lModels } = useQuery<MlModel[]>({
    queryKey: ['ml-models'],
    queryFn: () => predictionsApi.models().then(r => r.data).catch(() => []),
  })
  const { data: logs = [], isLoading: lLogs } = useQuery<MlPredictionLog[]>({
    queryKey: ['ml-logs'],
    queryFn: () => predictionsApi.logs({ limit: PREDICTION_LOGS_LIMIT }).then(r => r.data).catch(() => []),
  })
  const { mutate: train, isPending: training } = useMutation({
    mutationFn: () => predictionsApi.train(),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['ml-models'] })
      const d = res.data
      if (d.status === 'skipped') {
        toast.warning(d.reason || t('risk_scores_page.no_se_pudo_entrenar'))
      } else {
        const base = t('risk_scores_page.modelo_entrenado', { version: d.version, n: d.samples || 0 })
        toast.success(d.accuracy_roc_auc ? `${base} (AUC ${d.accuracy_roc_auc})` : base)
      }
    },
    onError: e => toast.error(extractErr(e, t('risk_scores_page.error_entrenar'))),
  })

  // Backend devuelve {total_projects, risk_counts:{critical,high,medium,low}, at_risk_projects}
  // Antes la UI buscaba portfolio.projects / portfolio.summary que NO existen → 0 en todos los KPIs.
  const projects: MlPortfolioRiskProject[] = portfolio?.at_risk_projects || []
  const summary  = {
    total: portfolio?.total_projects || 0,
    critical: portfolio?.risk_counts?.critical || 0,
    high: portfolio?.risk_counts?.high || 0,
    medium: portfolio?.risk_counts?.medium || 0,
    low: portfolio?.risk_counts?.low || 0,
  }

  return (
    <div>
      {/* Portfolio KPIs */}
      <div className="ds-grid-stats rsc-kpis">
        <KpiCard icon={<Search size={16} />} label={t('risk_scores_page.kpi_analizados')} value={summary.total || 0} />
        <KpiCard icon={<AlertTriangle size={16} />} label={t('risk_scores_page.kpi_alto_critico')} value={(summary.high || 0) + (summary.critical || 0)} danger={(summary.high || 0) + (summary.critical || 0) > 0} />
        <KpiCard icon={<AlertCircle size={16} />} label={t('risk_scores_page.kpi_moderado')} value={summary.medium || 0} warning={(summary.medium || 0) > 0} />
        <KpiCard icon={<CheckCircle2 size={16} />} label={t('risk_scores_page.kpi_bajo')} value={summary.low || 0} />
      </div>

      {(portfolio?.without_data || 0) > 0 && (
        <p className="rsc-note">
          {t('riskscores.sin_datos_para_predecir', { n: portfolio?.without_data })}
        </p>
      )}

      {/* Projects risk list */}
      <div className="rsc-ml">
        <div className="ds-card ds-card--plano">
          <div className="rsc-card-head">
            {t('riskscores.cartera_de_proyectos_ml')}
          </div>
          {lPortfolio ? <div className="rsc-pad"><Spinner /></div> : projects.length === 0 ? (
            <EmptyState icon={<Brain size={28} />} title={t('riskscores.sin_predicciones_ml')} description={t('risk_scores_page.sin_predicciones_desc')} />
          ) : (
            <div className="rsc-scroll">
              {projects.map((p) => {
                const level = p.risk_level || 'low'
                return (
                  <div key={p.project_id} className={`rsc-ml-row rsc-lvl--${level}`}>
                    <span className="rsc-dot" aria-hidden="true" />
                    <div className="u-flex1-min0">
                      <div className="rsc-ml-row__name rsc-ellipsis">{p.project_name}</div>
                      {p.recommendation && (
                        <div className="u-text3-xs-mt2 rsc-reco-ml"><Lightbulb size={12} aria-hidden /> {p.recommendation}</div>
                      )}
                    </div>
                    <div className="rsc-ml-row__meta">
                      {p.cpi != null && <span className="u-text3-xs">CPI {p.cpi?.toFixed(2)}</span>}
                      {p.spi != null && <span className="u-text3-xs">SPI {p.spi?.toFixed(2)}</span>}
                      <span className="rsc-pill">{nivelMl(level)}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Right panel: models + training + logs */}
        <div className="u-stack-12">
          {/* Train */}
          <div className="rsc-panel">
            <div className="rsc-panel__title">{t('risk_scores_page.entrenar_modelo')}</div>
            <div className="rsc-panel__text">
              {t('riskscores.usa_el_historial_de_proyectos_cerrados_para')}
            </div>
            <div className="rsc-full">
              <Button icon={<Brain size={14} />} onClick={() => train()} loading={training}>
                {training ? t('risk_scores_page.entrenando') : t('risk_scores_page.entrenar_ahora')}
              </Button>
            </div>
          </div>

          {/* Models */}
          <div className="ds-card ds-card--plano">
            <div className="rsc-card-head rsc-card-head--sm">
              {t('riskscores.versiones_del_modelo')}
            </div>
            <div className="rsc-scroll rsc-scroll--models">
              {lModels ? <div className="rsc-pad--sm"><Spinner /></div> : models.length === 0 ? (
                <div className="rsc-empty-mini">{t('riskscores.sin_modelos_entrenados')}</div>
              ) : models.map((m, i) => (
                <div key={m.id || i} className="rsc-mini-row">
                  <div className="u-row-between">
                    <span className="rsc-strong">v{m.version || i + 1}</span>
                    {m.is_active && <span className="rsc-active">{t('risk_scores_page.activo')}</span>}
                  </div>
                  <div className="rsc-sub">
                    {t('risk_scores_page.n_muestras', { n: m.samples_used || 0 })} · {m.trained_at ? fmtDate(m.trained_at) : ''}
                    {m.accuracy != null && <span> · AUC {Number(m.accuracy).toFixed(2)}</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Logs */}
          <div className="ds-card ds-card--plano">
            <div className="rsc-card-head rsc-card-head--sm">
              {t('riskscores.historial_de_predicciones')}
            </div>
            <div className="rsc-scroll rsc-scroll--logs">
              {lLogs ? <div className="rsc-pad--sm"><Spinner /></div> : logs.length === 0 ? (
                <div className="rsc-empty-mini">{t('riskscores.sin_predicciones_registradas')}</div>
              ) : logs.map((l, i) => {
                const level = l.risk_level || 'low'
                return (
                  <div key={l.id || i} className={`rsc-mini-row rsc-mini-row--xs rsc-lvl--${level}`}>
                    <div className="u-row-between">
                      <span className="rsc-log-name rsc-ellipsis">{l.project_name || l.project_id}</span>
                      <span className="rsc-log-level">{nivelMl(level)}</span>
                    </div>
                    <div className="rsc-sub">{l.predicted_at ? fmtDateTime(l.predicted_at) : ''}</div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function RiskScoresPage() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [tab, setTab] = useState<'rules' | 'ml'>('rules')
  const [selected, setSelected] = useState<string | number | null>(null)
  const [filterLevel, setFilterLevel] = useState<RiskLevel | 'all'>('all')
  const diaMes = formateadorDeFecha({ day: '2-digit', month: '2-digit' })

  const { data: response, isLoading, isFetching } = useQuery<RiskScoresResponse>({
    queryKey: ['risk-scores'],
    queryFn: () => api.get('/risk-scores').then(r => r.data as RiskScoresResponse),
  })
  const { data: detail } = useQuery<RiskDetail>({
    queryKey: ['risk-detail', selected],
    queryFn: () => api.get(`/risk-scores/${selected}`).then(r => r.data as RiskDetail),
    enabled: !!selected,
  })
  const { mutate: refresh, isPending:refreshing } = useMutation({
    mutationFn: () => api.get('/risk-scores?refresh=true').then(r=>r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['risk-scores'] }),
    onError: e => toast.error(extractErr(e, t('risk_scores_page.error_generico'))),
  })

  const projects: RiskProject[] = response?.projects || []
  const summary: RiskSummary = response?.summary || {}

  const filtered: RiskProject[] = filterLevel === 'all' ? projects : projects.filter((p) => p.level === filterLevel)

  const DIMENSIONES = [
    { key: 'schedule_risk', label: t('risk_scores_page.dim_cronograma') },
    { key: 'budget_risk', label: t('risk_scores_page.dim_presupuesto') },
    { key: 'scope_risk', label: t('risk_scores_page.dim_alcance') },
    { key: 'resource_risk', label: t('risk_scores_page.dim_recursos') },
  ] as const

  const radarData: RadarDatum[] = detail
    ? DIMENSIONES.map(d => ({ subject: d.label, A: Math.round(detail[d.key] || 0) }))
    : []

  const NIVELES: RiskLevel[] = ['critical', 'high', 'medium', 'low']

  return (
    <PageShell>
      <PageHeader
        icon={<AlertOctagon size={18} />}
        title={t('risk_scores.title')}
        subtitle={t('risk_scores.subtitle')}
        showListExport={tab === 'rules' && filtered.length > 0}
        exportTargetSelector='[data-export-table="risk-scores-list"]'
        exportFilePrefix='risk_scores'
        actions={tab === 'rules' ? (
          <Button variant="secondary" icon={<RefreshCw size={14} />} onClick={() => refresh()} loading={refreshing || isFetching}>
            {refreshing || isFetching ? t('risk_scores_page.recalculando') : t('risk_scores_page.recalcular_todo')}
          </Button>
        ) : undefined}
      />

      <Tabs
        items={[
          { id: 'rules', label: t('risk_scores_page.tab_senales'), icon: <ShieldAlert size={14} /> },
          { id: 'ml', label: t('risk_scores_page.tab_ml'), icon: <Brain size={14} /> },
        ]}
        active={tab}
        onChange={id => setTab(id as 'rules' | 'ml')}
        ariaLabel={t('risk_scores.title')}
        className="rsc-tabs"
      />

      {tab === 'ml' && <MLPredictionsTab />}

      {tab === 'rules' && <>
      {/* Summary KPIs */}
      <div className="ds-grid-stats rsc-kpis">
        {NIVELES.map((level) => (
          <KpiCard key={level} icon={LEVEL_ICON[level]} label={t(`risk_scores_page.riesgo_${level}`)} value={summary[level] || 0}
            danger={(level === 'critical' || level === 'high') && (summary[level] || 0) > 0}
            warning={level === 'medium' && (summary[level] || 0) > 0} />
        ))}
      </div>

      <div className="ds-toolbar rsc-toolbar">
        <Select suelto placeholder={false} className="rsc-filtro" aria-label={t('risk_scores_page.filtrar_nivel')}
          value={filterLevel} onChange={e => setFilterLevel(e.target.value as RiskLevel | 'all')}>
          <option value="all">{t('risk_scores_page.todos_niveles')}</option>
          {NIVELES.map(level => <option key={level} value={level}>{t(`risk_scores_page.riesgo_${level}`)}</option>)}
        </Select>
        {filterLevel !== 'all' && (
          <Button variant="ghost" icon={<X size={14} />} onClick={() => setFilterLevel('all')}>
            {t('risk_scores_page.quitar_filtro')}
          </Button>
        )}
      </div>

      <div className={`rsc-layout${selected ? ' rsc-layout--detail' : ''}`}>
        {/* Lista de proyectos */}
        <div>
          {isLoading ? <Spinner /> : filtered.length === 0 ? (
            <EmptyState icon={<ShieldCheck size={28} />} title={t('riskscores.sin_datos_de_riesgo')} description={t('risk_scores_page.sin_datos_desc')} />
          ) : (
            <div data-export-table="risk-scores-list" className="u-stack-8">
              {filtered.map((p) => {
                const level = p.level || 'low'
                const isSelected = selected === p.project_id
                return (
                  <Pulsable key={p.project_id} type="button" aria-pressed={isSelected}
                    onClick={() => setSelected(isSelected ? null : p.project_id)}
                    className={`rsc-project rsc-lvl--${level}`}>
                    <div className="u-row-center-12">
                      <span className="rsc-project__icon" aria-hidden="true">{LEVEL_ICON[level]}</span>
                      <div className="u-flex1">
                        <div className="rsc-project__head">
                          <div>
                            <span className="rsc-project__name">{p.project_name}</span>
                            <span className="rsc-code">{p.project_code}</span>
                          </div>
                          <div className="u-row-center-10">
                            <span className="rsc-pill rsc-pill--square">{t(`risk_scores_page.nivel_${level}`)}</span>
                            <span className="rsc-score">{Math.round(p.overall_score || 0)}</span>
                            <span className="u-text3-xs">/100</span>
                          </div>
                        </div>
                        <div className="rsc-dims">
                          {DIMENSIONES.map((d) => {
                            const val = p[d.key] || 0
                            return (
                              <div key={d.key}>
                                <div className="rsc-dim__label">{d.label}</div>
                                <div className="rsc-track">
                                  <div className={`rsc-fill rsc-fill--${tono(val)}`} style={anchura(val)} />
                                </div>
                                <div className="rsc-dim__value">{Math.round(val)}%</div>
                              </div>
                            )
                          })}
                        </div>
                        {p.recommendation && (
                          <div className="rsc-reco"><Lightbulb size={12} aria-hidden /> {p.recommendation}</div>
                        )}
                      </div>
                    </div>
                    {(p.delay_probability_pct ?? 0) > 20 && (
                      <div className="rsc-delay">
                        <span>{t('risk_scores_page.prob_retraso')}: <strong className="u-danger">{Math.round(p.delay_probability_pct ?? 0)}%</strong></span>
                        {p.predicted_delay_weeks && (
                          <span>{t('risk_scores_page.retraso_estimado')}: <strong className="u-warning">{t('risk_scores_page.n_semanas', { n: p.predicted_delay_weeks })}</strong></span>
                        )}
                        <span className="u-text3">{t('risk_scores_page.calculado', { fecha: p.computed_at ? fmtDateTime(p.computed_at) : '—' })}</span>
                      </div>
                    )}
                  </Pulsable>
                )
              })}
            </div>
          )}
        </div>

        {/* Panel detalle */}
        {selected && detail && (
          <aside className="rsc-detail" aria-label={detail.project_name}>
            <div className="u-row-between-mb16">
              <div className="rsc-detail__title">{detail.project_name}</div>
              <IconButton type="button" onClick={() => setSelected(null)} className="rsc-close"
                ariaLabel={t('risk_scores_page.cerrar_detalle')} title={t('risk_scores_page.cerrar_detalle')}>
                <X size={16} aria-hidden />
              </IconButton>
            </div>

            {/* Radar chart */}
            <ResponsiveContainer width="100%" height={200}>
              <RadarChart data={radarData}>
                <PolarGrid stroke="var(--surface-4)" />
                <PolarAngleAxis dataKey="subject" tick={{ fontSize: "var(--text-xs)", fill:'var(--text-2)' }} />
                <Radar name={detail.project_name} dataKey="A" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.25} />
                <Tooltip formatter={(v: unknown) => [`${Math.round(Number(v) || 0)}%`, t('risk_scores_page.riesgo')]} />
              </RadarChart>
            </ResponsiveContainer>

            <div className="rsc-mt16">
              <ScoreBar value={detail.schedule_risk || 0} label={t('riskscores.riesgo_de_cronograma')} />
              <ScoreBar value={detail.budget_risk || 0} label={t('riskscores.riesgo_de_presupuesto')} />
              <ScoreBar value={detail.scope_risk || 0} label={t('riskscores.riesgo_de_alcance')} />
              <ScoreBar value={detail.resource_risk || 0} label={t('riskscores.riesgo_de_recursos')} />
            </div>

            <div className="rsc-box">
              <div className="rsc-box__title">{t('riskscores.recomendacion')}</div>
              <div className="rsc-box__text">{detail.recommendation}</div>
            </div>

            {(detail.history?.length ?? 0) > 1 && (
              <div className="rsc-box rsc-box--tight">
                <div className="rsc-box__title">{t('riskscores.evolucion')}</div>
                <div className="rsc-history">
                  {detail.history!.map((h, i) => (
                    <span key={i} title={fmtDateTime(h.computed_at)}>{i > 0 && '→ '}<strong className="u-text1">{Math.round(h.overall_score)}</strong> <span className="u-text3">{diaMes.format(new Date(h.computed_at))}</span></span>
                  ))}
                </div>
              </div>
            )}

            {((detail.delay_probability_pct ?? 0) > 0) && (
              <div className="rsc-forecast">
                <div className="rsc-forecast__item">
                  <div className="rsc-forecast__value">{Math.round(detail.delay_probability_pct ?? 0)}%</div>
                  <div className="rsc-forecast__label">{t('risk_scores_page.prob_retraso')}</div>
                </div>
                <div className="rsc-forecast__item rsc-forecast__item--warning">
                  <div className="rsc-forecast__value">{t('risk_scores_page.n_semanas', { n: detail.predicted_delay_weeks || 0 })}</div>
                  <div className="rsc-forecast__label">{t('risk_scores_page.retraso_previsto')}</div>
                </div>
              </div>
            )}
          </aside>
        )}
      </div>
      </>}
    </PageShell>
  )
}
