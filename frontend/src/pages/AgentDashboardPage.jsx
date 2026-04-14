import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import api from '../services/api'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const ps = { background:'var(--surface-2)', border:'1px solid #1e2d45', borderRadius:12, padding:'20px 24px' }
const is = { width:'100%', background:'var(--surface-3)', border:'1px solid #1e2d45', borderRadius:8, padding:'8px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const TOOLTIP_STYLE = {background:'var(--surface-2)',border:'1px solid #1e2d45',borderRadius:8,color:'var(--text-1)',fontSize:12}

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
    queryFn: () => api.get(`/agent-dashboard/${agentId}?days=${days}`).then(r => r.data).catch(() => null),
    enabled: !!agentId,
  })

  const { mutate: snapshot, isPending: snapping } = useMutation({
    mutationFn: () => api.post(`/agent-dashboard/${agentId}/snapshot`).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['agent-dash', agentId, days]); toast.info('Snapshot creado') },
    onError: e => toast.error(extractErr(e, 'Error al crear snapshot')),
  })

  const trend = dash?.trend || []
  const kpis  = dash?.kpis || {}

  return (
    <div style={{padding:32}}>
      <PageHeader title={t('agent_dashboard.title')} subtitle="Métricas individuales de rendimiento: tickets, SLA y satisfacción por agente" />

      <div style={{...ps,marginBottom:20}}>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr auto auto',gap:12,alignItems:'flex-end'}}>
          <div>
            <label style={ls}>Agente</label>
            <select value={agentId} onChange={e => setAgentId(e.target.value)} style={is}>
              <option value="">Selecciona un agente...</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name || u.username}</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>Período</label>
            <select value={days} onChange={e => setDays(+e.target.value)} style={is}>
              <option value={7}>7 días</option>
              <option value={14}>14 días</option>
              <option value={30}>30 días</option>
              <option value={60}>60 días</option>
              <option value={90}>90 días</option>
            </select>
          </div>
          <Button onClick={() => snapshot()} disabled={!agentId || snapping}>
            {snapping ? '...' : '📸 Snapshot hoy'}
          </Button>
        </div>
      </div>

      {!agentId && <EmptyState icon="👤" title="Selecciona un agente" description="El dashboard muestra métricas individuales por agente de soporte" />}
      {agentId && isLoading && <Spinner />}

      {agentId && !isLoading && !dash && (
        <div style={{...ps,textAlign:'center',padding:'48px 24px'}}>
          <div style={{fontSize:48,marginBottom:16}}>📸</div>
          <div style={{fontSize:15,fontWeight:600,marginBottom:8}}>Sin datos históricos</div>
          <div style={{fontSize:13,color:'var(--text-2)',marginBottom:20}}>Crea el primer snapshot para este agente.</div>
          <Button onClick={() => snapshot()} disabled={snapping}>{snapping?'...':'Crear snapshot'}</Button>
        </div>
      )}

      {agentId && dash && (
        <div>
          {/* KPIs */}
          <div style={{display:'grid',gridTemplateColumns:'repeat(5,1fr)',gap:12,marginBottom:20}}>
            {[
              ['Tickets abiertos', dash.current?.open_tickets || 0, 'var(--text-1)'],
              ['Resueltos (período)', kpis.total_resolved || 0, 'var(--success)'],
              ['Tiempo medio (h)', kpis.avg_resolution_hours || 0, 'var(--accent)'],
              ['SLA compliance', `${kpis.sla_compliance_pct || 0}%`, kpis.sla_compliance_pct >= 90 ? 'var(--success)' : kpis.sla_compliance_pct >= 70 ? 'var(--warning)' : 'var(--danger)'],
              ['CSAT promedio', kpis.avg_csat ? kpis.avg_csat.toFixed(1) + '/5' : 'N/A', 'var(--purple)'],
            ].map(([label,val,color]) => (
              <div key={label} style={{...ps,padding:'14px 16px'}}>
                <div style={{fontSize:24,fontWeight:700,color}}>{val}</div>
                <div style={{fontSize:11,color:'var(--text-2)',textTransform:'uppercase',letterSpacing:'.07em'}}>{label}</div>
              </div>
            ))}
          </div>

          {trend.length === 0 ? (
            <div style={{...ps,textAlign:'center',padding:40,color:'var(--text-3)',fontSize:13}}>
              Sin datos de tendencia. Crea snapshots diariamente para ver la evolución.
            </div>
          ) : (
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16,marginBottom:16}}>
              <div style={ps}>
                <div style={{fontSize:13,fontWeight:600,marginBottom:16}}>Tickets resueltos por día</div>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={trend} margin={{top:5,right:10,left:0,bottom:0}}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" />
                    <XAxis dataKey="date" tick={{fill:'var(--text-2)',fontSize:10}} tickFormatter={d=>d.slice(5)} />
                    <YAxis tick={{fill:'var(--text-2)',fontSize:10}} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                    <Bar dataKey="resolved" name="Resueltos" fill="#00e5a0" radius={[4,4,0,0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div style={ps}>
                <div style={{fontSize:13,fontWeight:600,marginBottom:16}}>Cumplimiento SLA por día</div>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={trend} margin={{top:5,right:10,left:0,bottom:0}}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" />
                    <XAxis dataKey="date" tick={{fill:'var(--text-2)',fontSize:10}} tickFormatter={d=>d.slice(5)} />
                    <YAxis tick={{fill:'var(--text-2)',fontSize:10}} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                    <Bar dataKey="sla_ok"   name="Dentro SLA"  fill="#00e5a0" stackId="sla" radius={[0,0,0,0]} />
                    <Bar dataKey="sla_fail" name="Fuera SLA"   fill="#ff4757" stackId="sla" radius={[4,4,0,0]} />
                    <Legend wrapperStyle={{fontSize:11,color:'var(--text-2)'}} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {trend.some(d => d.csat !== null) && (
            <div style={ps}>
              <div style={{fontSize:13,fontWeight:600,marginBottom:16}}>CSAT diario</div>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={trend.filter(d=>d.csat!==null)} margin={{top:5,right:10,left:0,bottom:0}}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" />
                  <XAxis dataKey="date" tick={{fill:'var(--text-2)',fontSize:10}} tickFormatter={d=>d.slice(5)} />
                  <YAxis domain={[0,5]} tick={{fill:'var(--text-2)',fontSize:10}} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Line type="monotone" dataKey="csat" name="CSAT" stroke="#7c3aed" strokeWidth={2} dot={{r:3}} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          <div style={{...ps,marginTop:16,padding:'14px 18px'}}>
            <div style={{fontSize:12,color:'var(--text-3)',lineHeight:1.7}}>
              <strong style={{color:'var(--text-2)'}}>Instrucciones:</strong> Los snapshots se crean manualmente o vía cron en
              <code style={{color:'var(--accent)',marginLeft:6}}>POST /agent-dashboard/{'{agent_id}'}/snapshot</code>.
              Programa este endpoint diariamente para acumular métricas históricas.
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
