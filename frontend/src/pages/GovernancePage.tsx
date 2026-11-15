import { type CSSProperties, useState } from 'react'
import { extractErr, localeActivo } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { governanceApi, aiProvidersApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Shield } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'
import './GovernancePage.css'
import { TOOLTIP_SUPERFICIE_3_SM } from '../constants/estilosGrafico'

const MODULE_CFG: Record<string, { icon: string; labelKey: string; descKey: string }> = {
  nexusassist:          { icon: '💬', labelKey: 'governance.nexusassist_label',           descKey: 'governance.nexusassist_desc' },
  nexusagent:           { icon: '⚡', labelKey: 'governance.nexusagent_label',            descKey: 'governance.nexusagent_desc' },
  nexusoracle:          { icon: '🔮', labelKey: 'governance.nexusoracle_label',           descKey: 'governance.nexusoracle_desc' },
  meeting_assistant:    { icon: '🎙', labelKey: 'governance.meeting_assistant_label',     descKey: 'governance.meeting_assistant_desc' },
  sprint_planning:      { icon: '✨', labelKey: 'governance.sprint_planning_label',       descKey: 'governance.sprint_planning_desc' },
  contract_intelligence:{ icon: '📄', labelKey: 'governance.contract_intelligence_label', descKey: 'governance.contract_intelligence_desc' },
  knowledge_base:       { icon: '📚', labelKey: 'governance.knowledge_base_label',        descKey: 'governance.knowledge_base_desc' },
  portal_ai:            { icon: '🌐', labelKey: 'governance.portal_ai_label',             descKey: 'governance.portal_ai_desc' },
  voice:                { icon: '🎤', labelKey: 'governance.voice_label',                 descKey: 'governance.voice_desc' },
  mcp:                  { icon: '🔌', labelKey: 'governance.mcp_label',                   descKey: 'governance.mcp_desc' },
}

interface ProviderItem {
  name?: string
  is_default?: boolean
}

export default function GovernancePage(): JSX.Element {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [tab, setTab] = useState('modules')

  const { data: configs = [], isLoading: _loadingConfigs } = useQuery({
    queryKey: ['gov-config'],
    queryFn: () => governanceApi.config().then(r => r.data),
  })
  const { data: stats } = useQuery({
    queryKey: ['gov-stats'],
    queryFn: () => governanceApi.stats().then(r => r.data),
  })
  const { data: logs = [] } = useQuery({
    queryKey: ['gov-logs'],
    queryFn: () => governanceApi.logs().then(r => r.data),
    enabled: tab === 'audit',
  })
  const { data: providers = [] } = useQuery<ProviderItem[]>({
    queryKey: ['ai-providers'],
    queryFn: () => aiProvidersApi.list().then(r => r.data),
  })

  const { mutate: toggle } = useMutation({
    mutationFn: ({ module, is_enabled }: { module: string; is_enabled: boolean }) => governanceApi.update(module, { is_enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gov-config'] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const moduleEntries = stats?.by_module ? Object.entries(stats.by_module) : []
  const chartData = moduleEntries.length
    ? moduleEntries.map(([k, v]) => ({
        name: MODULE_CFG[k] ? t(MODULE_CFG[k].labelKey) : k,
        calls: v.calls || 0,
        tokens: Math.round((v.tokens || 0) / 1000),
      })).sort((a, b) => b.calls - a.calls)
    : []

  const _totalCalls  = chartData.reduce((a, d) => a + d.calls, 0)
  // Suma exacta (antes se redondeaba cada módulo a miles y unos cientos daban «0K»).
  const totalTokens = moduleEntries.reduce((a, [, v]) => a + (v.tokens || 0), 0)
  const tokensLegibles = totalTokens.toLocaleString(localeActivo())
  const activeCount = configs.filter(c => c.is_enabled).length
  const defaultProv = providers.find(p => p.is_default)

  return (
    <PageShell>
      <PageHeader icon={<Shield size={18} />} title={t('governance.title')} subtitle={t('governance.subtitle')} showListExport={false} />

      {/* KPIs */}
      <div className="gov-grid">
        {[
          { icon: '🤖', label: t('governance.kpi_active_modules'),   value: `${activeCount}/${configs.length || 9}`, color: 'var(--success)' },
          { icon: '💬', label: t('governance.kpi_total_calls'),  value: (stats?.total_calls || 0).toLocaleString(localeActivo()), color: 'var(--accent)' },
          { icon: '🔤', label: t('governance.kpi_tokens'),    value: tokensLegibles, color: 'var(--warning)' },
          { icon: '⚙️',  label: t('governance.kpi_active_provider'), value: defaultProv?.name || t('governance.kpi_not_configured'), color: defaultProv ? 'var(--success)' : 'var(--danger)' },
        ].map(k => (
          <div key={k.label} className="governance-page-e1">
            <div className="gov-box">{k.icon}</div>
            <div className="gov-box-2 governance-page-e2" style={{ '--governance-page-color': k.color } as CSSProperties}>{k.value}</div>
            <div className="u-text2-xs">{k.label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="gov-row">
        {[
          ['modules', `⚙️ ${t('governance.tab_modules')}`],
          ['usage', `📊 ${t('governance.tab_usage')}`],
          ['audit', `📋 ${t('governance.tab_audit')}`],
        ].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`gov-btn governan-sx1 ${tab === id ? 'governan-sx2' : 'governan-sx3'} governance-page-e3`} style={{ '--governance-page-border': `1px solid ${tab === id ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
            {label}
          </button>
        ))}
      </div>

      {/* MODULES TAB */}
      {tab === 'modules' && (
        <div className="gov-grid-2">
          {Object.entries(MODULE_CFG).map(([key, meta]) => {
            const cfg = configs.find(c => c.module === key)
            const isEnabled = cfg ? cfg.is_enabled : true
            const usage = stats?.by_module?.[key]
            return (
              <div key={key} className={`governance-page-e4 ${isEnabled ? 'governance-page-m5' : 'governance-page-m6'}`}>
                <div className="gov-row-2">
                  <div className="gov-row-3">
                    <span className="gov-label">{meta.icon}</span>
                    <div className="u-min0">
                      <div className="u-base-700">{t(meta.labelKey)}</div>
                      <div className="gov-box-3">{t(meta.descKey)}</div>
                    </div>
                  </div>
                  <div className="gov-row-4">
                    {usage && <span className="u-text2-xs">{t('pagina_gov.llamadas', { n: usage.calls || 0 })}</span>}
                    <button aria-label={t(meta.labelKey)} aria-pressed={isEnabled} onClick={() => toggle({ module: key, is_enabled: !isEnabled })}
                      className={`gov-btn-2 governan-sx4 ${isEnabled ? 'governan-sx5' : 'governan-sx6'} governance-page-e3`} style={{ '--governance-page-border': `1px solid ${isEnabled ? 'color-mix(in srgb, var(--success) 38%, transparent)' : 'var(--surface-4)'}` } as CSSProperties}>
                      <div className={`gov-box-4 ${isEnabled ? 'governan-sx7' : 'governan-sx8'}`} />
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* USAGE TAB */}
      {tab === 'usage' && (
        <div>
          {chartData.length === 0 ? (
            <div className="governance-page-e7">
              <div className="gov-box-5">📊</div>
              <div>{t('governance.no_usage_data')}</div>
            </div>
          ) : (
            <>
              <div className="governance-page-e8">
                <div className="gov-box-6">{t('governance.calls_by_module')}</div>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={chartData} margin={{ left: -10 }}>
                    <XAxis dataKey="name" tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} />
                    <YAxis tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} />
                    <Tooltip contentStyle={TOOLTIP_SUPERFICIE_3_SM} />
                    <Bar dataKey="calls" name="Llamadas" fill="var(--accent)" radius={[4, 4, 0, 0]}>
                      {chartData.map((_, i) => <Cell key={i} fill={['var(--accent)','var(--success)','var(--warning)','var(--purple)','var(--warning)','var(--danger)'][i % 6]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="governance-page-e9">
                <div className="gov-grid-3">
                  <span>{t('governance.col_module')}</span><span>{t('governance.col_calls')}</span><span>{t('governance.col_tokens')}</span>
                </div>
                {chartData.map((r, i) => (
                  <div key={i} className="gov-grid-4">
                    <span>{r.name}</span>
                    <span className="gov-label-2">{r.calls}</span>
                    <span className="u-warning">{r.tokens}K</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* AUDIT TAB */}
      {tab === 'audit' && (
        <div className="governance-page-e9">
          <div className="u-scroll-x">
          <div className="gov-box-7">
          <div className="gov-grid-5">
            <span>{t('governance.col_date')}</span><span>{t('governance.col_module')}</span><span>{t('governance.col_prompt')}</span><span>{t('governance.col_tokens')}</span>
          </div>
          {logs.length === 0 ? (
            <div className="gov-box-8">{t('governance.no_audit_logs')}</div>
          ) : logs.map(l => (
            <div key={l.id} className="gov-grid-6">
              <span className="u-text2-mono-xs">{l.created_at?.slice(0, 16)?.replace('T', ' ')}</span>
              <span className="gov-label-2">{MODULE_CFG[l.module ?? '']?.icon} {MODULE_CFG[l.module ?? ''] ? t(MODULE_CFG[l.module ?? ''].labelKey) : l.module}</span>
              <span className="gov-label-3">{l.action_type || t('governance.dash')}</span>
              <span className="u-warning">{(l.tokens_used || 0).toLocaleString(localeActivo())}</span>
            </div>
          ))}
          </div>
          </div>
        </div>
      )}
    </PageShell>
  )
}
