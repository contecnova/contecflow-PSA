/**
 * Gobernanza de IA: módulos (encender/apagar), uso por módulo y auditoría.
 *
 * 16-11-2026 (pasada de diseño): <Page>, KpiCard, Tabs y EmptyState comunes;
 * iconos lucide en lugar de emojis; fechas con el formateador de la app.
 */
import { type ReactNode, useState } from 'react'
import { extractErr, fmtDateTime, localeActivo } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { governanceApi, aiProvidersApi } from '../services/api'
import {
  AudioLines, BarChart3, BookOpen, Bot, ClipboardList, Cpu, FileText, GitPullRequest, Globe, MessageSquare, Mic, Plug,
  Settings, Shield, Sparkles, TrendingUp, Type, Zap,
} from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { Card, EmptyState, KpiCard, Page, Tabs, Switch } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import './GovernancePage.css'
import { TOOLTIP_SUPERFICIE_3_SM } from '../constants/estilosGrafico'

const MODULE_CFG: Record<string, { icon: ReactNode; labelKey: string; descKey: string }> = {
  nexusassist:          { icon: <MessageSquare size={18} />, labelKey: 'governance.nexusassist_label',           descKey: 'governance.nexusassist_desc' },
  nexusagent:           { icon: <Zap size={18} />,           labelKey: 'governance.nexusagent_label',            descKey: 'governance.nexusagent_desc' },
  nexusoracle:          { icon: <TrendingUp size={18} />,    labelKey: 'governance.nexusoracle_label',           descKey: 'governance.nexusoracle_desc' },
  meeting_assistant:    { icon: <Mic size={18} />,           labelKey: 'governance.meeting_assistant_label',     descKey: 'governance.meeting_assistant_desc' },
  sprint_planning:      { icon: <Sparkles size={18} />,      labelKey: 'governance.sprint_planning_label',       descKey: 'governance.sprint_planning_desc' },
  contract_intelligence:{ icon: <FileText size={18} />,      labelKey: 'governance.contract_intelligence_label', descKey: 'governance.contract_intelligence_desc' },
  knowledge_base:       { icon: <BookOpen size={18} />,      labelKey: 'governance.knowledge_base_label',        descKey: 'governance.knowledge_base_desc' },
  portal_ai:            { icon: <Globe size={18} />,         labelKey: 'governance.portal_ai_label',             descKey: 'governance.portal_ai_desc' },
  voice:                { icon: <AudioLines size={18} />,    labelKey: 'governance.voice_label',                 descKey: 'governance.voice_desc' },
  mcp:                  { icon: <Plug size={18} />,          labelKey: 'governance.mcp_label',                   descKey: 'governance.mcp_desc' },
  ticket_pr:            { icon: <GitPullRequest size={18} />, labelKey: 'governance.ticket_pr_label',            descKey: 'governance.ticket_pr_desc' },
}

const COLORES_BARRA = ['var(--accent)', 'var(--success)', 'var(--warning)', 'var(--purple)', 'var(--orange)', 'var(--danger)']

interface ProviderItem {
  name?: string
  is_default?: boolean
}

export default function GovernancePage(): JSX.Element {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [tab, setTab] = useState('modules')

  const { data: configs = [] } = useQuery({
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

  // Suma exacta (antes se redondeaba cada módulo a miles y unos cientos daban «0K»).
  const totalTokens = moduleEntries.reduce((a, [, v]) => a + (v.tokens || 0), 0)
  const tokensLegibles = totalTokens.toLocaleString(localeActivo())
  const activeCount = configs.filter(c => c.is_enabled).length
  const defaultProv = providers.find(p => p.is_default)

  const pestanas = [
    { id: 'modules', label: t('governance.tab_modules'), icon: <Settings size={14} /> },
    { id: 'usage', label: t('governance.tab_usage'), icon: <BarChart3 size={14} /> },
    { id: 'audit', label: t('governance.tab_audit'), icon: <ClipboardList size={14} /> },
  ]

  return (
    <Page icon={<Shield size={18} />} title={t('nav.governance')} subtitle={t('governance.subtitle')}>
      <div className="ds-grid-stats">
        <KpiCard icon={<Bot size={14} />} label={t('governance.kpi_active_modules')}
          value={`${activeCount}/${configs.length || Object.keys(MODULE_CFG).length}`} />
        <KpiCard icon={<MessageSquare size={14} />} label={t('governance.kpi_total_calls')}
          value={(stats?.total_calls || 0).toLocaleString(localeActivo())} />
        <KpiCard icon={<Type size={14} />} label={t('governance.kpi_tokens')} value={tokensLegibles} />
        <KpiCard icon={<Cpu size={14} />} label={t('governance.kpi_active_provider')}
          value={defaultProv?.name || t('governance.kpi_not_configured')} danger={!defaultProv} />
      </div>

      <Tabs items={pestanas} active={tab} onChange={setTab} ariaLabel={t('nav.governance')} />

      {/* MODULES TAB */}
      {tab === 'modules' && (
        <div className="gov-grid-2">
          {Object.entries(MODULE_CFG).map(([key, meta]) => {
            const cfg = configs.find(c => c.module === key)
            const isEnabled = cfg ? cfg.is_enabled : true
            const usage = stats?.by_module?.[key]
            return (
              <Card key={key}>
                <div className="gov-row-2">
                  <div className="gov-row-3">
                    <span className={`gov-label ${isEnabled ? 'gov-label--on' : ''}`} aria-hidden>{meta.icon}</span>
                    <div className="u-min0">
                      <div className="u-base-700">{t(meta.labelKey)}</div>
                      <div className="gov-box-3">{t(meta.descKey)}</div>
                    </div>
                  </div>
                  <div className="gov-row-4">
                    {usage && <span className="u-text2-xs">{t('pagina_gov.llamadas', { n: usage.calls || 0 })}</span>}
                    <Switch aria-label={t(meta.labelKey)} checked={isEnabled}
                      onChange={() => toggle({ module: key, is_enabled: !isEnabled })} />
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      {/* USAGE TAB */}
      {tab === 'usage' && (
        chartData.length === 0 ? (
          <EmptyState icon={<BarChart3 size={28} />} title={t('governance.no_usage_data')} />
        ) : (
          <>
            <Card>
              <div className="gov-box-6">{t('governance.calls_by_module')}</div>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartData} margin={{ left: -10 }}>
                  <XAxis dataKey="name" tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} />
                  <YAxis tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} />
                  <Tooltip contentStyle={TOOLTIP_SUPERFICIE_3_SM} />
                  <Bar dataKey="calls" name={t('governance.col_calls')} fill="var(--accent)" radius={[4, 4, 0, 0]}>
                    {chartData.map((_, i) => <Cell key={i} fill={COLORES_BARRA[i % COLORES_BARRA.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Card>
            <div className="gov-tabla">
              <div className="gov-grid-3">
                <span>{t('governance.col_module')}</span><span>{t('governance.col_calls')}</span><span>{t('governance.col_tokens')}</span>
              </div>
              {chartData.map((r, i) => (
                <div key={i} className="gov-grid-4">
                  <span className="u-min0">{r.name}</span>
                  <span className="gov-label-2">{r.calls}</span>
                  <span className="u-warning">{r.tokens}K</span>
                </div>
              ))}
            </div>
          </>
        )
      )}

      {/* AUDIT TAB */}
      {tab === 'audit' && (
        logs.length === 0 ? (
          <EmptyState icon={<ClipboardList size={28} />} title={t('governance.no_audit_logs')} />
        ) : (
          <div className="gov-tabla">
            <div className="u-scroll-x">
              <div className="gov-box-7">
                <div className="gov-grid-5">
                  <span>{t('governance.col_date')}</span><span>{t('governance.col_module')}</span><span>{t('governance.col_prompt')}</span><span>{t('governance.col_tokens')}</span>
                </div>
                {logs.map(l => (
                  <div key={l.id} className="gov-grid-6">
                    <span className="u-text2-xs">{fmtDateTime(l.created_at)}</span>
                    <span className="gov-label-2">{MODULE_CFG[l.module ?? ''] ? t(MODULE_CFG[l.module ?? ''].labelKey) : l.module}</span>
                    <span className="gov-label-3">{l.action_type || t('governance.dash')}</span>
                    <span className="u-warning">{(l.tokens_used || 0).toLocaleString(localeActivo())}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )
      )}
    </Page>
  )
}
