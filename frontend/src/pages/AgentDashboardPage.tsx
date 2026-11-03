import { useState } from 'react'
import type { ReactElement } from 'react'
import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { usersApi, cmdbApi } from '../services/api'
import { Spinner } from '../components/ui'
import { Page } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { BarChart2, User } from 'lucide-react'

interface UserItem {
  id: string | number
  full_name?: string
  username?: string
}

interface AgentTrendPoint {
  date: string
  resolved?: number
  sla_ok?: number
  sla_fail?: number
  csat?: number | null
}

interface AgentDashboardData {
  trend?: AgentTrendPoint[]
  kpis?: {
    total_resolved?: number
    avg_resolution_hours?: number
    sla_compliance_pct?: number
    avg_csat?: number
  }
  current?: { open_tickets?: number }
}

const TOOLTIP_STYLE = {
  background: 'var(--surface-2)',
  border: '1px solid var(--surface-4)',
  borderRadius: 'var(--radius-md)',
  color: 'var(--text-1)',
  fontSize: '12px',
}


export default function AgentDashboardPage(): JSX.Element {
  const t = useAppT()
  const [agentId, setAgentId] = useState('')
  const [_inputId, _setInputId] = useState('')
  const [days, setDays] = useState(30)

  const { data: users = [] } = useQuery<UserItem[]>({
    queryKey: ['users'],
    queryFn: () => usersApi.list({}).then(r => Array.isArray(r.data) ? (r.data as UserItem[]) : []).catch(() => []),
  })
  const { data: dash, isLoading } = useQuery<AgentDashboardData | null>({
    queryKey: ['agent-dash', agentId, days],
    queryFn: () => cmdbApi.agentDashboard(agentId, days).then(r => r.data).catch(() => null),
    enabled: !!agentId,
  })

  const trend = dash?.trend || []
  const kpis  = dash?.kpis || {}

  const ChartCard = ({ title, height, children }: { title?: string; height?: number; children: ReactElement }) => (
    <div className="ds-card">
      {title && <div style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--text-1)' }}>{title}</div>}
      <ResponsiveContainer width="100%" height={height || 200}>{children}</ResponsiveContainer>
    </div>
  )

  return (
    <Page
      icon={<BarChart2 size={18} />}
      title={t('agent_dashboard.title')}
      subtitle={t('agent_dashboard.subtitle')}
    >
      {/* Filters */}
      <div className="ds-card">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)', alignItems: 'flex-end' }}>
          <div className="ds-field">
            <label className="ds-field__label">{t('agent_dashboard.agent')}</label>
            <select value={agentId} onChange={e => setAgentId(e.target.value)} className="ds-input">
              <option value="">{t('agent_dashboard.select_agent')}</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name || u.username}</option>)}
            </select>
          </div>
          <div className="ds-field">
            <label className="ds-field__label">{t('agent_dashboard.period')}</label>
            <select value={days} onChange={e => setDays(+e.target.value)} className="ds-input">
              <option value={7}>7 {t('common.days')}</option>
              <option value={14}>14 {t('common.days')}</option>
              <option value={30}>30 {t('common.days')}</option>
              <option value={60}>60 {t('common.days')}</option>
              <option value={90}>90 {t('common.days')}</option>
            </select>
          </div>
        </div>
      </div>

      {!agentId && (
        <div className="ds-empty">
          <User size={36} className="ds-empty__icon" />
          <div className="ds-empty__title">{t('agent_dashboard.empty_title')}</div>
          <div className="ds-empty__desc">{t('agent_dashboard.empty_desc')}</div>
        </div>
      )}
      {agentId && isLoading && <div style={{ textAlign: 'center', padding: 'var(--space-8)' }}><Spinner /></div>}

      {agentId && !isLoading && !dash && (
        <div className="ds-empty">
          <BarChart2 size={36} className="ds-empty__icon" />
          <div className="ds-empty__title">{t('agent_dashboard.no_history')}</div>
        </div>
      )}

      {agentId && dash && (
        <>
          {/* KPI row */}
          <div className="ds-grid-stats">
            {([
              [t('agent_dashboard.kpi_open_tickets'), dash.current?.open_tickets || 0, 'var(--text-1)'],
              [t('agent_dashboard.kpi_resolved_period'), kpis.total_resolved || 0, 'var(--success)'],
              [t('agent_dashboard.kpi_avg_time_hours'), kpis.avg_resolution_hours || 0, 'var(--accent)'],
              [t('agent_dashboard.kpi_sla_compliance'), `${kpis.sla_compliance_pct || 0}%`,
                (kpis.sla_compliance_pct || 0) >= 90 ? 'var(--success)' : (kpis.sla_compliance_pct || 0) >= 70 ? 'var(--warning)' : 'var(--danger)'],
              [t('agent_dashboard.kpi_avg_csat'), kpis.avg_csat ? kpis.avg_csat.toFixed(1) + '/5' : t('agent_dashboard.no_data'), 'var(--purple)'],
            ] as Array<[string, string | number, string]>).map(([label, val, color]) => (
              <div key={label} className="ds-card">
                <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color, lineHeight: 1.1 }}>{val}</div>
                <div className="ds-eyebrow">{label}</div>
              </div>
            ))}
          </div>

          {/* Charts row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 'var(--space-3)' }}>
            <ChartCard title={t('agent_dashboard.chart_resolved_by_day')}>
              <BarChart data={trend} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="date" tick={{ fill: 'var(--text-2)', fontSize: 'var(--text-2xs)' }} tickFormatter={d => d.slice(5)} />
                <YAxis tick={{ fill: 'var(--text-2)', fontSize: 'var(--text-2xs)' }} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="resolved" name={t('agent_dashboard.kpi_resolved_period')} fill="var(--success)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ChartCard>

            <ChartCard title={t('agent_dashboard.chart_sla_by_day')}>
              <BarChart data={trend} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="date" tick={{ fill: 'var(--text-2)', fontSize: 'var(--text-2xs)' }} tickFormatter={d => d.slice(5)} />
                <YAxis tick={{ fill: 'var(--text-2)', fontSize: 'var(--text-2xs)' }} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="sla_ok" name={t('agent_dashboard.sla_within')} fill="var(--success)" stackId="sla" />
                <Bar dataKey="sla_fail" name={t('agent_dashboard.sla_outside')} fill="var(--danger)" stackId="sla" radius={[4, 4, 0, 0]} />
                <Legend wrapperStyle={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)' }} />
              </BarChart>
            </ChartCard>
          </div>

          {/* CSAT + helper */}
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--space-3)' }}>
            {trend.some((d) => d.csat != null) ? (
              <ChartCard title={t('agent_dashboard.chart_daily_csat')} height={180}>
                <LineChart data={trend.filter((d) => d.csat != null)} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text-2)', fontSize: 'var(--text-2xs)' }} tickFormatter={d => d.slice(5)} />
                  <YAxis domain={[0, 5]} tick={{ fill: 'var(--text-2)', fontSize: 'var(--text-2xs)' }} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Line type="monotone" dataKey="csat" name="CSAT" stroke="var(--purple)" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ChartCard>
            ) : (
              <div className="ds-card" style={{ alignItems: 'center', justifyContent: 'center', minHeight: 180, color: 'var(--text-3)' }}>
                {t('agent_dashboard.trend_no_data')}
              </div>
            )}
          </div>
        </>
      )}
    </Page>
  )
}
