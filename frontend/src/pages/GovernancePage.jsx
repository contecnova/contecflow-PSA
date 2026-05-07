import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { governanceApi, aiProvidersApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Shield } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'

const card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }

const MODULE_CFG = {
  nexusassist:          { icon: '💬', labelKey: 'governance.nexusassist_label',           descKey: 'governance.nexusassist_desc' },
  nexusagent:           { icon: '⚡', labelKey: 'governance.nexusagent_label',            descKey: 'governance.nexusagent_desc' },
  nexusoracle:          { icon: '🔮', labelKey: 'governance.nexusoracle_label',           descKey: 'governance.nexusoracle_desc' },
  meeting_assistant:    { icon: '🎙', labelKey: 'governance.meeting_assistant_label',     descKey: 'governance.meeting_assistant_desc' },
  sprint_planning:      { icon: '✨', labelKey: 'governance.sprint_planning_label',       descKey: 'governance.sprint_planning_desc' },
  contract_intelligence:{ icon: '📄', labelKey: 'governance.contract_intelligence_label', descKey: 'governance.contract_intelligence_desc' },
  knowledge_base:       { icon: '📚', labelKey: 'governance.knowledge_base_label',        descKey: 'governance.knowledge_base_desc' },
  portal_ai:            { icon: '🌐', labelKey: 'governance.portal_ai_label',             descKey: 'governance.portal_ai_desc' },
  voice:                { icon: '🎤', labelKey: 'governance.voice_label',                 descKey: 'governance.voice_desc' },
}

export default function GovernancePage() {
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
  const { data: providers = [] } = useQuery({
    queryKey: ['ai-providers'],
    queryFn: () => aiProvidersApi.list().then(r => r.data),
  })

  const { mutate: toggle } = useMutation({
    mutationFn: ({ module, is_enabled }) => governanceApi.update(module, { is_enabled }),
    onSuccess: () => qc.invalidateQueries(['gov-config']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const chartData = stats?.by_module
    ? Object.entries(stats.by_module).map(([k, v]) => ({
        name: MODULE_CFG[k] ? t(MODULE_CFG[k].labelKey) : k,
        calls: v.calls || 0,
        tokens: Math.round((v.tokens || 0) / 1000),
      })).sort((a, b) => b.calls - a.calls)
    : []

  const _totalCalls  = chartData.reduce((a, d) => a + d.calls, 0)
  const totalTokens = chartData.reduce((a, d) => a + d.tokens, 0)
  const activeCount = configs.filter(c => c.is_enabled).length
  const defaultProv = providers.find(p => p.is_default)

  return (
    <PageShell>
      <PageHeader icon={<Shield size={18} />} title={t('governance.title')} subtitle={t('governance.subtitle')} showListExport={false} />

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 24 }}>
        {[
          { icon: '🤖', label: t('governance.kpi_active_modules'),   value: `${activeCount}/${configs.length || 9}`, color: 'var(--success)' },
          { icon: '💬', label: t('governance.kpi_total_calls'),  value: (stats?.total_calls || 0).toLocaleString(), color: 'var(--accent)' },
          { icon: '🔤', label: t('governance.kpi_tokens'),    value: `${totalTokens}K`, color: 'var(--warning)' },
          { icon: '⚙️',  label: t('governance.kpi_active_provider'), value: defaultProv?.name || t('governance.kpi_not_configured'), color: defaultProv ? 'var(--success)' : 'var(--danger)' },
        ].map(k => (
          <div key={k.label} style={{ ...card, padding: '16px 20px' }}>
            <div style={{ fontSize: "var(--text-xl-em)", marginBottom: 4 }}>{k.icon}</div>
            <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 800, color: k.color, marginBottom: 2 }}>{k.value}</div>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{k.label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 20, borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        {[
          ['modules', `⚙️ ${t('governance.tab_modules')}`],
          ['usage', `📊 ${t('governance.tab_usage')}`],
          ['audit', `📋 ${t('governance.tab_audit')}`],
        ].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            style={{ padding: '5px 14px', borderRadius: 6, border: `1px solid ${tab === id ? 'var(--accent)' : 'var(--surface-4)'}`, background: tab === id ? 'var(--accent-muted)' : 'transparent', color: tab === id ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
      </div>

      {/* MODULES TAB */}
      {tab === 'modules' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
          {Object.entries(MODULE_CFG).map(([key, meta]) => {
            const cfg = configs.find(c => c.module === key)
            const isEnabled = cfg ? cfg.is_enabled : true
            const usage = stats?.by_module?.[key]
            return (
              <div key={key} style={{ ...card, padding: '16px 18px', opacity: isEnabled ? 1 : 0.6 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    <span style={{ fontSize: "var(--text-xl)" }}>{meta.icon}</span>
                    <div>
                      <div style={{ fontSize: "var(--text-base)", fontWeight: 700 }}>{t(meta.labelKey)}</div>
                      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2, lineHeight: 1.4 }}>{t(meta.descKey)}</div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0, marginLeft: 10 }}>
                    {usage && <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{usage.calls || 0} calls</span>}
                    <button onClick={() => toggle({ module: key, is_enabled: !isEnabled })}
                      style={{ width: 44, height: 24, borderRadius: 12, background: isEnabled ? 'var(--success-border)' : 'var(--surface-4)', border: `1px solid ${isEnabled ? 'rgba(52,211,153,0.38)' : 'var(--surface-4)'}`, cursor: 'pointer', position: 'relative', transition: 'all 0.2s' }}>
                      <div style={{ width: 18, height: 18, borderRadius: 9, background: isEnabled ? 'var(--success)' : 'var(--text-2)', position: 'absolute', top: 2, left: isEnabled ? 22 : 2, transition: 'all 0.2s' }} />
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
            <div style={{ ...card, padding: 48, textAlign: 'center', color: 'var(--text-2)' }}>
              <div style={{ fontSize: "var(--text-4xl)", marginBottom: 12 }}>📊</div>
              <div>{t('governance.no_usage_data')}</div>
            </div>
          ) : (
            <>
              <div style={{ ...card, padding: '20px 24px', marginBottom: 16 }}>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 16 }}>{t('governance.calls_by_module')}</div>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={chartData} margin={{ left: -10 }}>
                    <XAxis dataKey="name" tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} />
                    <YAxis tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} />
                    <Tooltip contentStyle={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', fontSize: "var(--text-sm)" }} />
                    <Bar dataKey="calls" name="Llamadas" fill="var(--accent)" radius={[4, 4, 0, 0]}>
                      {chartData.map((_, i) => <Cell key={i} fill={['var(--accent)','var(--success)','var(--warning)','var(--purple)','var(--warning)','var(--danger)'][i % 6]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div style={{ ...card, overflow: 'hidden' }}>
                <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--surface-4)', display: 'grid', gridTemplateColumns: '1fr 100px 100px', gap: 16, fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase' }}>
                  <span>{t('governance.col_module')}</span><span>{t('governance.col_calls')}</span><span>{t('governance.col_tokens')}</span>
                </div>
                {chartData.map((r, i) => (
                  <div key={i} style={{ padding: '12px 20px', borderBottom: '1px solid var(--surface-4)30', display: 'grid', gridTemplateColumns: '1fr 100px 100px', gap: 16, fontSize: "var(--text-base)" }}>
                    <span>{r.name}</span>
                    <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{r.calls}</span>
                    <span style={{ color: 'var(--warning)' }}>{r.tokens}K</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* AUDIT TAB */}
      {tab === 'audit' && (
        <div style={{ ...card, overflow: 'hidden' }}>
          <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--surface-4)', display: 'grid', gridTemplateColumns: '160px 120px 1fr 80px', gap: 16, fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase' }}>
            <span>{t('governance.col_date')}</span><span>{t('governance.col_module')}</span><span>{t('governance.col_prompt')}</span><span>{t('governance.col_tokens')}</span>
          </div>
          {logs.length === 0 ? (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-2)', fontSize: "var(--text-base)" }}>{t('governance.no_audit_logs')}</div>
          ) : logs.map(l => (
            <div key={l.id} style={{ padding: '10px 20px', borderBottom: '1px solid var(--surface-4)20', display: 'grid', gridTemplateColumns: '160px 120px 1fr 80px', gap: 16, fontSize: "var(--text-sm)", alignItems: 'center' }}>
              <span style={{ color: 'var(--text-2)', fontFamily: 'var(--font-mono)', fontSize: "var(--text-xs)" }}>{l.created_at?.slice(0, 16)?.replace('T', ' ')}</span>
              <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{MODULE_CFG[l.module]?.icon} {MODULE_CFG[l.module] ? t(MODULE_CFG[l.module].labelKey) : l.module}</span>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-2)' }}>{l.input_summary || l.action_type || t('governance.dash')}</span>
              <span style={{ color: 'var(--warning)' }}>{(l.tokens_used || 0).toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
    </PageShell>
  )
}
