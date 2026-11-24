import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, fmtNumber, localeActivo } from '../utils/helpers'
import { useState, type CSSProperties } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { predictiveObservabilityApi, aiProvidersApi } from '../services/api'
import type { ProveedorIa as AiProvider, CatalogoIa as ProviderCatalog, EstadisticasIa as AiStats, DiagnosticoIa as Diagnostics } from '../services/api/tipos-grc'
import { Button, Spinner, Tabs, Page, KpiCard, EmptyState, EstadoDeError, StatusBadge, SelectorDePeriodo, IconButton } from '../components/ui'
import { sanitizeUrl } from '../utils/security'
import { usePeriodo } from '../hooks/usePeriodo'
import { CON_HORA, codigoDeErrorDePeriodo } from '../utils/periodo'
import { useAppLang, useAppT } from '../i18n/AppLangContext'
import { Cpu, X, Search, Plus, Activity, RefreshCw, Shield, Plug, Download, Star, KeyRound, AlertTriangle, ExternalLink, CheckCircle2, HelpCircle, Play, Server, MessageSquare, Coins, Route, BarChart3, BookOpen } from 'lucide-react'
import './AIHubPage.css'
import { STALE_REFERENCE_DATA_MS } from '../constants/timings'
import { PDOCS, PMETA, STATUS_KEYS, colorVar } from './AIHubComun'
import { ProviderModal, TestModal } from './AIHubProveedores'
import { GastoDeHoy, GovernanceTab, RoutingTab } from './AIHubGobierno'

export default function AIHubPage(): JSX.Element {
  const traducir = useAppT()
  const { lang } = useAppLang()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  // `{}` abre el alta; un proveedor abre la edición.
  const [modal, setModal] = useState<Partial<AiProvider> | null>(null)
  const [testModal, setTestModal] = useState<AiProvider | null>(null)
  const [tab, setTab] = useState('providers')
  const [diagResults, setDiagResults] = useState<Diagnostics | null>(null)

  const { mutate: importarEntorno } = useMutation({
    mutationFn: () => aiProvidersApi.importEnv(),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ai-providers'] }); toast.success(t('aihub.imported')) },
    onError: e => toast.error(extractErr(e, t('aihub.import_error'))),
  })
  const { data: providers = [], isLoading } = useQuery<AiProvider[]>({
    queryKey: ['ai-providers'],
    queryFn: () => aiProvidersApi.list().then(r => r.data),
    select: d => (Array.isArray(d) ? d : []),
  })
  const { data: catalog = {} } = useQuery<ProviderCatalog>({
    queryKey: ['ai-providers-catalog'],
    queryFn: () => aiProvidersApi.catalog().then(r => r.data),
    staleTime: Infinity,
  })
  const { data: stats } = useQuery<AiStats>({
    queryKey: ['ai-stats'],
    queryFn: () => aiProvidersApi.stats().then(r => r.data),
    enabled: tab === 'stats',
  })
  // Periodo libre (16-11-2026): ventana de evaluación del modelo ITSM (antes
  // 30 días fijos; la API aceptaba `lookback_days`). El modelo BI no depende de ella.
  const periodoObs = usePeriodo({ defecto: '30d', granularidades: CON_HORA, prefijo: 'obs' })
  const { data: obsHealth, isLoading: obsLoading, error: obsError } = useQuery({
    queryKey: ['predictive-obs-health', periodoObs.params],
    // 23-11-2026: sin `.catch` que devolvía null; el error de periodo se explica y los demás se pintan con EstadoDeError.
    queryFn: () => predictiveObservabilityApi.health({ ...periodoObs.params }).then(r => r.data),
    enabled: tab === 'observability',
    staleTime: STALE_REFERENCE_DATA_MS,
  })
  const obsErrorDePeriodo = codigoDeErrorDePeriodo(obsError)
  const { mutate: triggerRetrain, isPending: retraining } = useMutation({
    mutationFn: () => predictiveObservabilityApi.triggerRetrain(),
    onSuccess: () => { toast.success(t('aihub.retrain_done')); qc.invalidateQueries({ queryKey: ['predictive-obs-health'] }) },
    onError: e => toast.error(extractErr(e, t('aihub.retrain_error'))),
  })

  const { mutate: setDefault } = useMutation({
    mutationFn: (id: string) => aiProvidersApi.setDefault(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ai-providers'] }),
    onError: e => toast.error(extractErr(e, t('ai.reset_error'))),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id: string) => aiProvidersApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ai-providers'] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const { mutate: diagnoseAll, isPending: diagnosing } = useMutation({
    mutationFn: () => aiProvidersApi.diagnostics().then(r => r.data),
    onSuccess: (data: Diagnostics) => {
      setDiagResults(data)
      const healthy = Number(data?.healthy || 0)
      const total = Number(data?.total || 0)
      if (healthy === total) {
        toast.success(t('aihub.diag_ok', { total }))
      } else {
        toast.error(t('aihub.diag_partial', { healthy, total }))
      }
    },
    onError: e => toast.error(extractErr(e, t('aihub.diag_error'))),
  })

  const { mutate: syncAllModels, isPending: syncingAllModels } = useMutation({
    mutationFn: () => aiProvidersApi.syncAll().then(r => r.data),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['ai-providers'] })
      const failed = Number(data?.failed || 0)
      const total = Number(data?.total || 0)
      if (failed > 0) {
        toast.error(t('aihub.sync_partial', { ok: total - failed, total }))
      } else {
        toast.success(t('aihub.sync_all_ok', { total }))
      }
    },
    onError: e => toast.error(extractErr(e, t('aihub.sync_all_error'))),
  })

  const defaultProvider = providers.find(p => p.is_default)
  const byModule = stats?.by_module || []
  // USD a proposito (auditoria 2026-11, #18): los proveedores de IA facturan y
  // publican precios en dolares y el backend guarda el gasto en `*_cost_usd`
  // (presupuesto AI_DAILY_BUDGET_USD). Convertirlo a la moneda de la empresa
  // seria inventar un tipo de cambio.
  const moneyFmt = new Intl.NumberFormat(localeActivo(lang), { style: 'currency', currency: 'USD', minimumFractionDigits: 4, maximumFractionDigits: 4 })
  const intFmt = new Intl.NumberFormat(localeActivo(lang))

  return (
    <Page
      icon={<Cpu size={18} />}
      title={t('nav.ai_hub')}
      subtitle={t('ai.hub_subtitle')}
      rightActions={(
        <div className="aih-header-actions">
          <Button
            variant="secondary"
            onClick={() => diagnoseAll()}
            disabled={diagnosing}
            loading={diagnosing}
            icon={<Search size={14} />}
          >
            {diagnosing ? t('aihub.diagnosing') : t('aihub.diagnose')}
          </Button>
          <Button
            variant="secondary"
            onClick={() => syncAllModels()}
            disabled={syncingAllModels}
            loading={syncingAllModels}
            icon={<RefreshCw size={14} />}
          >
            {syncingAllModels ? t('aihub.syncing_models') : t('aihub.sync_all_models')}
          </Button>
          <Button onClick={() => setModal({})} icon={<Plus size={14} />}>
            {t('ai.add_provider')}
          </Button>
        </div>
      )}
    >
      <GastoDeHoy />
      {/* Tabs */}
      <Tabs
        items={[
          { id: 'providers',     label: t('ai.providers'), icon: <Cpu size={14} /> },
          { id: 'routing',       label: t('aihub.tab_routing'), icon: <Route size={14} /> },
          { id: 'stats',         label: t('ai.usage'), icon: <BarChart3 size={14} /> },
          { id: 'governance',    label: t('aihub.tab_governance'), icon: <Shield size={14} /> },
          { id: 'observability', label: t('aihub.tab_observability'), icon: <Activity size={14} /> },
          { id: 'guide',         label: t('ai.guide'), icon: <BookOpen size={14} /> },
        ]}
        active={tab}
        onChange={setTab}
        ariaLabel={t('ai.hub_title')}
        className="aih-tabs"
      />

      {tab === 'governance' && <GovernanceTab />}
      {tab === 'routing' && <RoutingTab providers={providers} />}

      {/* PROVIDERS TAB */}
      {tab === 'providers' && (
        <div id="aihub-panel-providers" role="tabpanel" aria-labelledby="aihub-tab-providers">

          {/* Panel de diagnóstico */}
          {diagResults && (
            <div role="status" className={`aih-card aih-card--pad-md aih-diag aih-tone--${diagResults.error > 0 ? 'danger' : diagResults.warning > 0 ? 'warning' : 'success'}`}>
              <div className="aih-diag-head">
                <div className="u-md-700">
                  {traducir('aihub.diagnostico_resumen', { healthy: diagResults.healthy, total: diagResults.total })}
                </div>
                <IconButton variante="caja" onClick={() => setDiagResults(null)} ariaLabel={t('common.close')}><X size={16} aria-hidden="true" /></IconButton>
              </div>
              <div className="u-stack-8">
                {(diagResults.providers || []).map(pr => {
                  const dotKind = pr.status === 'ok' ? 'success' : pr.status === 'warning' ? 'warning' : 'danger'
                  return (
                    <div key={pr.id} className="aih-diag-row">
                      <span className={`ds-status-dot ds-status-dot--${dotKind}`} aria-hidden="true" />
                      <div className="u-flex1-min0">
                        <span className="u-600">{pr.name}</span>
                        <span className="aih-diag-meta">{PMETA[pr.provider_type]?.name || pr.provider_type}</span>
                        {pr.latency_ms != null && (
                          <span className="aih-diag-meta">{fmtNumber(pr.latency_ms, 0)} ms</span>
                        )}
                        {pr.models_found > 0 && (
                          <span className="aih-diag-meta">{t('aihub.n_models', { count: pr.models_found })}</span>
                        )}
                        {pr.error && (
                          <div className={pr.status === 'warning' ? 'aih-diag-error aih-diag-error--warning' : 'aih-diag-error'}>{pr.error}</div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Proveedor activo */}
          {defaultProvider && (
            <div className="aih-card aih-card--pad-md aih-active" style={colorVar(PMETA[defaultProvider.provider]?.color)}>
              <div className="u-row-center-12">
                <span className="aih-active-icon" aria-hidden="true"><Cpu size={24} /></span>
                <div className="u-min0">
                  <div className="aih-active-eyebrow">{t('ai.provider_active_default')}</div>
                  <div className="aih-active-name">{defaultProvider.name}</div>
                  <div className="u-text2-sm">{t('ai.provider_resumen', { modelo: defaultProvider.default_model, n: intFmt.format(defaultProvider.total_requests || 0), coste: moneyFmt.format(defaultProvider.total_cost_usd || 0) })}</div>
                </div>
              </div>
            </div>
          )}

          {isLoading ? <Spinner /> : providers.length === 0 ? (
            <div className="ds-card">
              <EmptyState
                icon={<Cpu size={28} />}
                title={t('ai.no_providers_title')}
                description={t('ai.no_providers_desc')}
                action={<Button onClick={() => setModal({})} icon={<Plus size={14} />}>{t('ai.add_provider')}</Button>}
              />
            </div>
          ) : (
            <div data-export-table="ai-providers-list" className="aih-providers">
              {providers.map(p => {
                const meta: { name?: string; color: string } = PMETA[p.provider] || { color: 'var(--text-2)' }
                const st = (STATUS_KEYS as readonly string[]).includes(p.status) ? p.status : 'inactive'
                return (
                  <div key={p.id} className={`aih-card aih-card--pad${p.is_default ? ' aih-provider--default' : ''}`} style={colorVar(meta.color)}>
                    <div className="aih-provider-head">
                      <div className="aih-provider-id">
                        <div className="aih-provider-logo" aria-hidden="true">
                          <Cpu size={20} />
                        </div>
                        <div className="u-min0">
                          <div className="u-md-700">{p.name}</div>
                          <div className="u-text2-xs">{meta.name} · {p.default_model || t('ai.model_none')}</div>
                        </div>
                      </div>
                      <div className="aih-provider-badges">
                        <StatusBadge kind={st === 'active' ? 'success' : st === 'error' ? 'danger' : 'neutral'} caps={false}>{t(`ai.provider_status_${st}`)}</StatusBadge>
                        {p.is_default && <StatusBadge kind="accent" caps={false}><Star size={11} aria-hidden="true" /> {t('ai.default_badge')}</StatusBadge>}
                        {p.source === 'env' && <StatusBadge caps={false} title={t('aihub.from_env_help')}>{t('aihub.from_env')}</StatusBadge>}
                      </div>
                    </div>

                    <div className={`aih-provider-key${!p.has_api_key && p.provider !== 'ollama' ? ' aih-provider-key--warn' : ''}`}>
                      {p.has_api_key
                        ? <><KeyRound size={13} aria-hidden="true" /> {t('ai.api_key_configured')}</>
                        : p.provider === 'ollama'
                          ? <><Server size={13} aria-hidden="true" /> {t('ai.local_no_key')}</>
                          : <><AlertTriangle size={13} aria-hidden="true" /> {t('ai.no_api_key')}</>}
                      {p.last_error && <span className="aih-provider-key-error">· {t('common.error')}: {p.last_error.slice(0, 40)}...</span>}
                    </div>

                    <div className="aih-provider-usage">
                      <div><span className="u-text2">{t('ai.requests')}:</span> <strong>{intFmt.format(p.total_requests || 0)}</strong></div>
                      <div><span className="u-text2">{t('ai.total_cost')}:</span> <strong className="u-warning">{moneyFmt.format(Number(p.total_cost_usd || 0))}</strong></div>
                    </div>

                    <div className="u-wrap-6">
                      <Button variant="secondary" size="sm" icon={<Plug size={14} />} title={`${t('ai.provider_test_aria')} ${p.name}`} onClick={() => setTestModal(p)}>
                        {t('ai.provider_test_action')}
                      </Button>
                      {p.source === 'env' && (
                        <Button variant="secondary" size="sm" icon={<Download size={14} />} title={t('aihub.import_help')} onClick={() => importarEntorno()}>
                          {t('aihub.import_btn')}
                        </Button>
                      )}
                      {p.source !== 'env' && !p.is_default && (
                        <Button variant="secondary" size="sm" icon={<Star size={14} />} title={`${t('ai.provider_default_aria')} ${p.name}`} onClick={() => setDefault(p.id)}>
                          {t('ai.provider_default_action')}
                        </Button>
                      )}
                      {p.source !== 'env' && <>
                      <Button variant="ghost" size="sm" title={`${t('ai.provider_edit_aria')} ${p.name}`} onClick={() => setModal(p)}>
                        {t('ai.provider_edit_action')}
                      </Button>
                      <Button variant="danger" size="sm" title={`${t('ai.provider_delete_action')} ${p.name}`} onClick={() => { openConfirmGlobal({ message: `${t('ai.delete_confirm')} "${p.name}"?`, onConfirm: () => del(p.id), danger: true }) }}>
                        {t('ai.provider_delete_action')}
                      </Button>
                      </>}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* STATS TAB */}
      {tab === 'stats' && (
        <div id="aihub-panel-stats" role="tabpanel" aria-labelledby="aihub-tab-stats">
          <div className="ds-grid-stats aih-stats">
            <KpiCard icon={<Cpu size={16} />} label={t('ai.providers_count')} value={intFmt.format((stats?.providers || []).length)} />
            <KpiCard icon={<MessageSquare size={16} />} label={t('ai.total_requests')} value={intFmt.format(stats?.total_requests || 0)} />
            <KpiCard icon={<Coins size={16} />} label={t('ai.total_cost')} value={moneyFmt.format(stats?.total_cost || 0)} />
          </div>

          {byModule.length > 0 && (
            <div className="aih-card">
              <div className="aih-module-head">{t('ai.module_usage')}</div>
              {byModule.map(r => (
                <div key={r.module} className="aih-module-row">
                  <span className="u-600">{r.module}</span>
                  <div className="aih-module-nums">
                    <span>{intFmt.format(r.calls || 0)} {t('ai.calls')}</span>
                    <span>{intFmt.format(r.tokens || 0)} {t('ai.tokens_label')}</span>
                    <span className="u-warning">{moneyFmt.format(r.cost || 0)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* OBSERVABILITY TAB */}
      {tab === 'observability' && (
        <div className="u-stack-16">
          <div className="aih-obs-head">
            <div className="u-text2-base">{traducir('aihub.estado_de_salud_de_los_modelos_predictivos')}</div>
            <Button onClick={() => triggerRetrain()} disabled={retraining} loading={retraining} icon={<Play size={14} />}>
              {retraining ? t('aihub.retraining') : t('aihub.force_retrain')}
            </Button>
          </div>
          <SelectorDePeriodo {...periodoObs.selector} sinGranularidad />

          {obsLoading ? <Spinner /> : obsErrorDePeriodo ? (
            <EmptyState icon={<AlertTriangle size={28} />} title={t(`periodo_err.${obsErrorDePeriodo.motivo}`, obsErrorDePeriodo.params)} />
          ) : obsError ? (
            <EstadoDeError error={obsError} onReintentar={() => { void qc.invalidateQueries({ queryKey: ['predictive-obs-health'] }) }} />
          ) : !obsHealth ? (
            <div className="ds-card">
              <EmptyState icon={<Activity size={28} />} title={traducir('aihub.obs_empty_title')} description={traducir('aihub.sin_datos_de_observabilidad_requiere_permisos_de')} />
            </div>
          ) : (
            <div className="aih-two-cols">
              {[
                { key: 'itsm', label: t('aihub.model_itsm'), data: obsHealth.itsm },
                { key: 'bi',   label: t('aihub.model_bi'),   data: obsHealth.bi },
              ].map(({ key, label, data }) => {
                if (!data) return null
                const salud = data.status === 'healthy' || data.status === 'attention' ? data.status : 'other'
                const estado = data.status ? t(`aihub.health_${data.status}`, data.status) : t('aihub.health_unknown')
                return (
                  <div key={key} className={`aih-card aih-card--pad aih-health--${salud}`}>
                    <div className="aih-model-head">
                      <div className="u-md-600">{label}</div>
                      <StatusBadge kind={salud === 'healthy' ? 'success' : salud === 'attention' ? 'warning' : 'neutral'} caps={false}>
                        {estado}
                      </StatusBadge>
                    </div>
                    {data.score != null && (
                      <div className="u-mb-10">
                        <div className="aih-score-head">
                          <span className="u-text2">{traducir('aihub.score_de_salud')}</span>
                          <span className="aih-score-value">{fmtNumber(data.score * 100, 0)}%</span>
                        </div>
                        <div className="aih-bar" role="progressbar" aria-label={traducir('aihub.score_de_salud')} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(Math.min(data.score * 100, 100))}>
                          <div className="aih-bar-fill" style={{ '--pct': `${Math.min(data.score * 100, 100)}%` } as CSSProperties} />
                        </div>
                      </div>
                    )}
                    <div className="aih-facts">
                      {/* Auditoría 2026-11: la API da samples, severity_accuracy y mae_minutes
                          (ITSM) e history_months y motores (BI); no total_predictions/accuracy. */}
                      {data.samples != null && (
                        <div className="aih-fact">
                          <span className="u-text3">{t('aihub.fact_predictions')}</span>
                          <span>{fmtNumber(data.samples, 0)}</span>
                        </div>
                      )}
                      {data.severity_accuracy != null && (
                        <div className="aih-fact">
                          <span className="u-text3">{traducir('aihub.precision')}</span>
                          <span>{fmtNumber(data.severity_accuracy * 100, 1)}%</span>
                        </div>
                      )}
                      {data.mae_minutes != null && (
                        <div className="aih-fact">
                          <span className="u-text3">{t('aihub.fact_mae')}</span>
                          <span>{t('aihub.minutes_short', { n: fmtNumber(data.mae_minutes, 1) })}</span>
                        </div>
                      )}
                      {data.status && (
                        <div className="aih-fact">
                          <span className="u-text3">{t('common.status')}</span>
                          <span>{estado}</span>
                        </div>
                      )}
                      {/* Revisión 2026-11: leía drift_detected y reason, que la API no da; el modelo BI da
                          meses de historia y el motor usado (los «fallback»/«heuristic» bajan la nota). */}
                      {data.history_months != null && (
                        <div className="aih-fact">
                          <span className="u-text3">{t('aihub.fact_history_months')}</span>
                          <span>{fmtNumber(data.history_months, 0)}</span>
                        </div>
                      )}
                      {data.forecast_engine && (
                        <div className="aih-fact">
                          <span className="u-text3">{t('aihub.fact_engines')}</span>
                          <span>{t(`aihub.engine_${data.forecast_engine}`, data.forecast_engine)} · {data.overrun_engine ? t(`aihub.engine_${data.overrun_engine}`, data.overrun_engine) : '—'}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {obsHealth && (
            <div className={`aih-card aih-overall aih-health--${obsHealth.overall_status === 'healthy' || obsHealth.overall_status === 'attention' ? obsHealth.overall_status : 'other'}`}>
              <div className="aih-overall-icon" aria-hidden="true">
                {obsHealth.overall_status === 'healthy' ? <CheckCircle2 size={24} /> : obsHealth.overall_status === 'attention' ? <AlertTriangle size={24} /> : <HelpCircle size={24} />}
              </div>
              <div>
                <div className="u-base-600">{t('aihub.overall_status')}: {obsHealth.overall_status ? t(`aihub.health_${obsHealth.overall_status}`, obsHealth.overall_status) : t('aihub.health_unknown')}</div>
                <div className="u-text2-sm-mt2">
                  {t('aihub.overall_score')}: {obsHealth.overall_score != null ? `${fmtNumber(obsHealth.overall_score * 100, 0)}%` : '—'}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* GUIDE TAB */}
      {tab === 'guide' && (
        <div className="aih-two-cols">
          {[
            { key: 'anthropic', title: t('ai.guide_anthropic'), desc: t('ai.guide_anthropic_desc'), link: PDOCS.anthropic, hint: 'sk-ant-...' },
            { key: 'openai', title: t('ai.guide_openai'), desc: t('ai.guide_openai_desc'), link: PDOCS.openai, hint: 'sk-...' },
            { key: 'gemini', title: t('ai.guide_gemini'), desc: t('ai.guide_gemini_desc'), link: PDOCS.gemini, hint: 'AIza...' },
            { key: 'deepseek', title: t('ai.guide_deepseek'), desc: t('ai.guide_deepseek_desc'), link: PDOCS.deepseek, hint: 'sk-...' },
            { key: 'groq', title: t('ai.guide_groq'), desc: t('ai.guide_groq_desc'), link: PDOCS.groq, hint: 'gsk_...' },
            { key: 'mistral', title: t('ai.guide_mistral'), desc: t('ai.guide_mistral_desc'), link: PDOCS.mistral, hint: '...' },
            { key: 'ollama', title: t('ai.guide_ollama'), desc: t('ai.guide_ollama_desc'), link: PDOCS.ollama, hint: t('ai.no_api_key') },
            { key: 'azure', title: t('ai.guide_azure'), desc: t('ai.guide_azure_desc'), link: PDOCS.azure, hint: `(${t('ai.azure_api_key_hint')})` },
          ].map(p => (
            <div key={p.key} className="aih-card aih-card--pad" style={colorVar(PMETA[p.key]?.color)}>
              <div className="aih-guide-head">
                <span className="aih-guide-icon" aria-hidden="true"><Cpu size={18} /></span>
                <div>
                  <div className="u-md-700">{p.title}</div>
                  <div className="aih-guide-desc">{p.desc}</div>
                </div>
              </div>
              <div className="aih-guide-foot">
                <span className="u-text3-mono-xs">{p.hint}</span>
                <a href={sanitizeUrl(p.link)} target="_blank" rel="noreferrer" className="aih-link aih-link--icon">{t('ai.get_key')} <ExternalLink size={12} aria-hidden="true" /></a>
              </div>
            </div>
          ))}
        </div>
      )}

      {modal !== null && (
        <ProviderModal
          provider={Object.keys(modal).length ? modal : null}
          catalog={catalog}
          onClose={() => setModal(null)}
        />
      )}
      {testModal && <TestModal provider={testModal} onClose={() => setTestModal(null)} />}
    </Page>
  )
}
