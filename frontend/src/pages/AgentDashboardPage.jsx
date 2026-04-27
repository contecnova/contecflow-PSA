import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import api from '../services/api'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'
import { BarChart2 } from 'lucide-react'

const ps = {
  background: 'var(--surface-2)',
  border: '1px solid var(--surface-4)',
  borderRadius: 'var(--radius-lg)',
  padding: 'var(--space-6) var(--space-8)',
}
const is = {
  width: '100%',
  background: 'var(--surface-3)',
  border: '1px solid var(--surface-4)',
  borderRadius: 'var(--radius-md)',
  padding: 'var(--space-3) var(--space-3)',
  color: 'var(--text-1)',
  fontSize: '13px',
  outline: 'none',
  fontFamily: 'var(--font-sans)',
  boxSizing: 'border-box',
}
const ls = {
  fontSize: '11px',
  fontWeight: 600,
  color: 'var(--text-2)',
  textTransform: 'uppercase',
  letterSpacing: '0.07em',
  display: 'block',
  marginBottom: 'var(--space-1)',
}

const TOOLTIP_STYLE = {
  background: 'var(--surface-2)',
  border: '1px solid var(--surface-4)',
  borderRadius: 'var(--radius-md)',
  color: 'var(--text-1)',
  fontSize: '12px',
}


export default function AgentDashboardPage() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [agentId, setAgentId] = useState('')
  const [_inputId, _setInputId] = useState('')
  const [days, setDays] = useState(30)

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => api.get('/users').then(r => Array.isArray(r.data) ? r.data : []).catch(() => []),
  })
  const { data: dash, isLoading } = useQuery({
    queryKey: ['agent-dash', agentId, days],
    queryFn: () => api.get(`/cmdb/agent-dashboard/${agentId}?days=${days}`).then(r => r.data).catch(() => null),
    enabled: !!agentId,
  })

  const { mutate: snapshot, isPending: snapping } = useMutation({
    mutationFn: () => api.post(`/cmdb/agent-dashboard/${agentId}/snapshot`).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['agent-dash', agentId, days]); toast.info(t('agent_dashboard.snapshot_created')) },
    onError: e => toast.error(extractErr(e, t('agent_dashboard.snapshot_create_error'))),
  })

  const trend = dash?.trend || []
  const kpis  = dash?.kpis || {}

  const renderWidget = (id) => {
    switch (id) {
      case 'kpis':
        return (
          <div style={{...ps,padding:'14px 16px'}}>
            <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit, minmax(180px, 1fr))',gap:12}}>
              {[
                [t('agent_dashboard.kpi_open_tickets'), dash.current?.open_tickets || 0, 'var(--text-1)'],
                [t('agent_dashboard.kpi_resolved_period'), kpis.total_resolved || 0, 'var(--success)'],
                [t('agent_dashboard.kpi_avg_time_hours'), kpis.avg_resolution_hours || 0, 'var(--accent)'],
                [t('agent_dashboard.kpi_sla_compliance'), `${kpis.sla_compliance_pct || 0}%`, kpis.sla_compliance_pct >= 90 ? 'var(--success)' : kpis.sla_compliance_pct >= 70 ? 'var(--warning)' : 'var(--danger)'],
                [t('agent_dashboard.kpi_avg_csat'), kpis.avg_csat ? kpis.avg_csat.toFixed(1) + '/5' : t('agent_dashboard.no_data'), 'var(--purple)'],
              ].map(([label,val,color]) => (
                <div key={label} style={{...ps,padding:'14px 16px'}}>
                  <div style={{fontSize:24,fontWeight:700,color}}>{val}</div>
                  <div style={{fontSize:11,color:'var(--text-2)',textTransform:'uppercase',letterSpacing:'.07em'}}>{label}</div>
                </div>
              ))}
            </div>
          </div>
        )
      case 'resolved':
        return (
          <div style={ps}>
            <div style={{fontSize:13,fontWeight:600,marginBottom:16}}>{t('agent_dashboard.chart_resolved_by_day')}</div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={trend} margin={{top:5,right:10,left:0,bottom:0}}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="date" tick={{fill:'var(--text-2)',fontSize:10}} tickFormatter={d=>d.slice(5)} />
                <YAxis tick={{fill:'var(--text-2)',fontSize:10}} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="resolved" name={t('agent_dashboard.kpi_resolved_period')} fill="#00e5a0" radius={[4,4,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )
      case 'sla':
        return (
          <div style={ps}>
            <div style={{fontSize:13,fontWeight:600,marginBottom:16}}>{t('agent_dashboard.chart_sla_by_day')}</div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={trend} margin={{top:5,right:10,left:0,bottom:0}}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="date" tick={{fill:'var(--text-2)',fontSize:10}} tickFormatter={d=>d.slice(5)} />
                <YAxis tick={{fill:'var(--text-2)',fontSize:10}} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="sla_ok" name={t('agent_dashboard.sla_within')} fill="#00e5a0" stackId="sla" radius={[0,0,0,0]} />
                <Bar dataKey="sla_fail" name={t('agent_dashboard.sla_outside')} fill="#ff4757" stackId="sla" radius={[4,4,0,0]} />
                <Legend wrapperStyle={{fontSize:11,color:'var(--text-2)'}} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )
      case 'csat':
        return trend.some(d => d.csat !== null) ? (
          <div style={ps}>
            <div style={{fontSize:13,fontWeight:600,marginBottom:16}}>{t('agent_dashboard.chart_daily_csat')}</div>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={trend.filter(d=>d.csat!==null)} margin={{top:5,right:10,left:0,bottom:0}}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="date" tick={{fill:'var(--text-2)',fontSize:10}} tickFormatter={d=>d.slice(5)} />
                <YAxis domain={[0,5]} tick={{fill:'var(--text-2)',fontSize:10}} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Line type="monotone" dataKey="csat" name="CSAT" stroke="#7c3aed" strokeWidth={2} dot={{r:3}} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div style={{...ps,textAlign:'center',padding:40,color:'var(--text-3)',fontSize:13}}>
            {t('agent_dashboard.trend_no_data')}
          </div>
        )
      case 'instructions':
        return (
          <div style={{...ps,padding:'14px 18px'}}>
            <div style={{fontSize:12,color:'var(--text-3)',lineHeight:1.7}}>
              <strong style={{color:'var(--text-2)'}}>{t('agent_dashboard.instructions_label')}:</strong> {t('agent_dashboard.instructions_text')}
              <code style={{color:'var(--accent)',marginLeft:6}}>POST /agent-dashboard/{'{agent_id}'}/snapshot</code>.
            </div>
          </div>
        )
      default:
        return null
    }
  }

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        icon={<BarChart2 size={18} />}
        title={t('agent_dashboard.title')}
        subtitle={t('agent_dashboard.subtitle')}
        actions={
          <Button onClick={() => snapshot()} disabled={!agentId || snapping}>
            {snapping ? '...' : `📸 ${t('agent_dashboard.snapshot_today')}`}
          </Button>
        }
      />

      {/* Filters */}
      <div style={{ ...ps, marginBottom: 20 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 12, alignItems: 'flex-end' }}>
          <div>
            <label style={ls}>{t('agent_dashboard.agent')}</label>
            <select value={agentId} onChange={e => setAgentId(e.target.value)} style={is}>
              <option value="">{t('agent_dashboard.select_agent')}</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name || u.username}</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>{t('agent_dashboard.period')}</label>
            <select value={days} onChange={e => setDays(+e.target.value)} style={is}>
              <option value={7}>7 {t('common.days')}</option>
              <option value={14}>14 {t('common.days')}</option>
              <option value={30}>30 {t('common.days')}</option>
              <option value={60}>60 {t('common.days')}</option>
              <option value={90}>90 {t('common.days')}</option>
            </select>
          </div>
          <Button onClick={() => snapshot()} disabled={!agentId || snapping}>
            {snapping ? '...' : `📸 ${t('agent_dashboard.snapshot_today')}`}
          </Button>
        </div>
      </div>

      {!agentId && <EmptyState icon="👤" title={t('agent_dashboard.empty_title')} description={t('agent_dashboard.empty_desc')} />}
      {agentId && isLoading && <Spinner />}

      {agentId && !isLoading && !dash && (
        <div style={{ ...ps, textAlign: 'center', padding: '48px 24px' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>📸</div>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>{t('agent_dashboard.no_history')}</div>
          <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 20 }}>{t('agent_dashboard.no_history_desc')}</div>
          <Button onClick={() => snapshot()} disabled={snapping}>{snapping ? '...' : t('agent_dashboard.create_snapshot')}</Button>
        </div>
      )}

      {agentId && dash && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {renderWidget('kpis')}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            {renderWidget('resolved')}
            {renderWidget('sla')}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
            {renderWidget('csat')}
            {renderWidget('instructions')}
          </div>
        </div>
      )}
    </div>
  )
}
