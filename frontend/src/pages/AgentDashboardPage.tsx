import { useState, useId } from 'react'
import type { CSSProperties, ReactElement } from 'react'
import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { usersApi, cmdbApi, type UserListItem } from '../services/api'
import { Spinner } from '../components/ui'
import { Page } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { BarChart2, User } from 'lucide-react'
import { fmtNumber } from '../utils/helpers'
import './AgentDashboardPage.css'
import { LEYENDA_XS } from '../constants/estilosGrafico'

const TOOLTIP_STYLE = {
  background: 'var(--surface-2)',
  border: '1px solid var(--surface-4)',
  borderRadius: 'var(--radius-md)',
  color: 'var(--text-1)',
  fontSize: 'var(--text-sm)',
}


export default function AgentDashboardPage(): JSX.Element {
  const idCampo = useId()
  const t = useAppT()
  const [agentId, setAgentId] = useState('')
  const [_inputId, _setInputId] = useState('')
  const [days, setDays] = useState(30)

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list({}).then(r => r.data).catch((): UserListItem[] => []),
  })
  const { data: dash, isLoading } = useQuery({
    queryKey: ['agent-dash', agentId, days],
    queryFn: () => cmdbApi.agentDashboard(agentId, days).then(r => r.data).catch(() => null),
    enabled: !!agentId,
  })

  const trend = dash?.trend || []
  const kpis  = dash?.kpis

  const ChartCard = ({ title, height, children }: { title?: string; height?: number; children: ReactElement }) => (
    <div className="ds-card">
      {title && <div className="u-text1-base-600">{title}</div>}
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
        <div className="agd-filters">
          <div className="ds-field">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="ds-field__label">{t('agent_dashboard.agent')}</label>
            <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={agentId} onChange={e => setAgentId(e.target.value)} className="ds-input">
              <option value="">{t('agent_dashboard.select_agent')}</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
            </select>
          </div>
          <div className="ds-field">
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="ds-field__label">{t('agent_dashboard.period')}</label>
            <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={days} onChange={e => setDays(+e.target.value)} className="ds-input">
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
      {agentId && isLoading && <div className="agd-loading"><Spinner /></div>}

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
              [t('agent_dashboard.kpi_avg_csat'), kpis.avg_csat ? fmtNumber(kpis.avg_csat, 1) + '/5' : t('agent_dashboard.no_data'), 'var(--purple)'],
            ] as Array<[string, string | number, string]>).map(([label, val, color]) => (
              <div key={label} className="ds-card">
                <div className="agd-kpi-value" style={{ '--kpi-color': color } as CSSProperties}>{val}</div>
                <div className="ds-eyebrow">{label}</div>
              </div>
            ))}
          </div>

          {/* Charts row */}
          <div className="agd-charts">
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
                <Legend wrapperStyle={LEYENDA_XS} />
              </BarChart>
            </ChartCard>
          </div>

          {/* CSAT + helper */}
          <div className="agd-csat-row">
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
              <div className="ds-card agd-no-trend">
                {t('agent_dashboard.trend_no_data')}
              </div>
            )}
          </div>
        </>
      )}
    </Page>
  )
}
