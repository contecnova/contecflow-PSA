import { useState, useId } from 'react'
import type { ReactElement } from 'react'
import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { cmdbApi } from '../services/api'
import { useListaDeUsuarios } from '../hooks/useListas'
import { Spinner, Page, KpiCard, EmptyState, EstadoDeError, SelectorDePeriodo, Select } from '../components/ui'
import { usePeriodo } from '../hooks/usePeriodo'
import { CON_HORA, codigoDeErrorDePeriodo, formatearTramo } from '../utils/periodo'
import { useAppT } from '../i18n/AppLangContext'
import { BarChart2, CheckCircle2, Clock, Inbox, ShieldCheck, Star, User } from 'lucide-react'
import { fmtNumber } from '../utils/helpers'
import { useTono } from '../hooks/useOrgSettings'
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
  const tono = useTono()
  const [agentId, setAgentId] = useState('')
  const [_inputId, _setInputId] = useState('')
  // Periodo libre (16-11-2026): antes 7/14/30/60/90 días propios y tendencia siempre por día.
  const periodo = usePeriodo({ defecto: '30d', granularidades: CON_HORA })

  // 23-11-2026 (04 A8): lista compartida de personas (antes `['users']` con `.catch` que guardaba `[]`).
  const { data: users = [] } = useListaDeUsuarios()
  const { data: dash, isLoading, error, refetch } = useQuery({
    queryKey: ['agent-dash', agentId, periodo.params],
    // Los errores de periodo se muestran traducidos; el resto, con EstadoDeError (antes: «sin datos»).
    queryFn: () => cmdbApi.agentDashboard(agentId, { ...periodo.params }).then(r => r.data),
    enabled: !!agentId,
  })
  const errorDePeriodo = codigoDeErrorDePeriodo(error)
  const eje = (v: unknown) => formatearTramo(String(v), periodo.granularidad)
  const etiquetaLarga = (v: unknown) => formatearTramo(String(v), periodo.granularidad, true)

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
      title={t('nav.agent_dashboard')}
      subtitle={t('agent_dashboard.subtitle')}
    >
      {/* Filters */}
      <div className="ds-card">
        <div className="agd-filters">
          <Select label={t('agent_dashboard.agent')} placeholder={false} id={`${idCampo}-1`} value={agentId} onChange={e => setAgentId(e.target.value)}>
              <option value="">{t('agent_dashboard.select_agent')}</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
            </Select>
          <div className="ds-field">
            <span className="uiinde-estiloetiqueta">{t('agent_dashboard.period')}</span>
            <SelectorDePeriodo {...periodo.selector} />
          </div>
        </div>
      </div>

      {!agentId && (
        <div className="ds-card">
          <EmptyState
            icon={<User size={28} />}
            title={t('agent_dashboard.empty_title')}
            description={t('agent_dashboard.empty_desc')}
          />
        </div>
      )}
      {agentId && isLoading && <div className="agd-loading"><Spinner /></div>}

      {agentId && errorDePeriodo && (
        <div className="ds-card">
          <EmptyState icon={<BarChart2 size={28} />} title={t(`periodo_err.${errorDePeriodo.motivo}`, errorDePeriodo.params)} />
        </div>
      )}

      {agentId && error && !errorDePeriodo && <EstadoDeError error={error} onReintentar={() => { void refetch() }} />}

      {agentId && !isLoading && !dash && !error && (
        <div className="ds-card">
          <EmptyState
            icon={<BarChart2 size={28} />}
            title={t('agent_dashboard.no_history')}
            description={t('agent_dashboard.no_history_desc')}
          />
        </div>
      )}

      {agentId && dash && (
        <>
          {/* KPI row */}
          <div className="ds-grid-stats">
            <KpiCard icon={<Inbox size={16} />} label={t('agent_dashboard.kpi_open_tickets')} value={dash.current?.open_tickets || 0} />
            <KpiCard icon={<CheckCircle2 size={16} />} label={t('agent_dashboard.kpi_resolved_period')} value={kpis.total_resolved || 0} accent />
            <KpiCard icon={<Clock size={16} />} label={t('agent_dashboard.kpi_avg_time_hours')} value={kpis.avg_resolution_hours || 0} />
            <KpiCard
              icon={<ShieldCheck size={16} />}
              label={t('agent_dashboard.kpi_sla_compliance')}
              value={`${kpis.sla_compliance_pct || 0}%`}
              danger={tono('sla', kpis.sla_compliance_pct || 0) === 'danger'}
              warning={tono('sla', kpis.sla_compliance_pct || 0) === 'warning'}
            />
            <KpiCard icon={<Star size={16} />} label={t('agent_dashboard.kpi_avg_csat')} value={kpis.avg_csat ? fmtNumber(kpis.avg_csat, 1) + '/5' : t('agent_dashboard.no_data')} />
          </div>

          {/* Charts row */}
          <div className="agd-charts">
            <ChartCard title={t('agent_dashboard.chart_resolved_by_day')}>
              <BarChart data={trend} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="t" tick={{ fill: 'var(--text-2)', fontSize: 'var(--text-2xs)' }} tickFormatter={eje} />
                <YAxis tick={{ fill: 'var(--text-2)', fontSize: 'var(--text-2xs)' }} />
                <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={etiquetaLarga} />
                <Bar dataKey="resolved" name={t('agent_dashboard.kpi_resolved_period')} fill="var(--success)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ChartCard>

            <ChartCard title={t('agent_dashboard.chart_sla_by_day')}>
              <BarChart data={trend} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="t" tick={{ fill: 'var(--text-2)', fontSize: 'var(--text-2xs)' }} tickFormatter={eje} />
                <YAxis tick={{ fill: 'var(--text-2)', fontSize: 'var(--text-2xs)' }} />
                <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={etiquetaLarga} />
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
                  <XAxis dataKey="t" tick={{ fill: 'var(--text-2)', fontSize: 'var(--text-2xs)' }} tickFormatter={eje} />
                  <YAxis domain={[0, 5]} tick={{ fill: 'var(--text-2)', fontSize: 'var(--text-2xs)' }} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={etiquetaLarga} />
                  <Line type="monotone" dataKey="csat" name="CSAT" stroke="var(--purple)" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ChartCard>
            ) : (
              <div className="ds-card">
                <EmptyState icon={<Star size={28} />} title={t('agent_dashboard.chart_daily_csat')} description={t('agent_dashboard.trend_no_data')} />
              </div>
            )}
          </div>
        </>
      )}
    </Page>
  )
}
