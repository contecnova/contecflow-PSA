/**
 * ExecutiveDashboardPage — Vista C-Level
 * KPIs financieros, salud de proyectos, utilización equipo, pipeline, NPS
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api, { dashboardApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { fmtCurrency } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'
import { Spinner } from '../components/ui'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, CartesianGrid
} from 'recharts'

const _COLORS = ['#00d4ff','#7c3aed','#1d9e75','#ef9f27','#e24b4a']

function KpiCard({ icon, label, value, sub, color='var(--accent)', trend }) {
  return (
    <div style={{ background:'var(--surface-2)', border:'1px solid #1e2d45',
      borderRadius:12, padding:'18px 20px' }}>
      <div style={{ fontSize:22, marginBottom:8 }}>{icon}</div>
      <div style={{ fontSize:28, fontWeight:900, color,
        fontFamily:"'Space Mono',monospace", marginBottom:2 }}>{value}</div>
      <div style={{ fontSize:12, fontWeight:700, color:'var(--text-1)' }}>{label}</div>
      {sub && <div style={{ fontSize:11, color:'var(--text-2)', marginTop:2 }}>{sub}</div>}
      {trend !== undefined && (
        <div style={{ fontSize:11, marginTop:4,
          color: trend >= 0 ? 'var(--success)' : 'var(--danger)' }}>
          {trend >= 0 ? '↑' : '↓'} {Math.abs(trend)}% vs mes ant.
        </div>
      )}
    </div>
  )
}

const panel = {
  background:'var(--surface-2)', border:'1px solid #1e2d45',
  borderRadius:12, padding:'20px 22px'
}

export default function ExecutiveDashboardPage() {
  const _t = useAppT()
  const [period, _setPeriod] = useState('month')

  const { data: kpis, isLoading: kpisLoading } = useQuery({
    queryKey: ['exec-kpis'],
    queryFn: () => dashboardApi.kpis().then(r => r.data).catch(() => ({})),
  })
  const { data: health = [], isLoading: healthLoading } = useQuery({
    queryKey: ['exec-health'],
    queryFn: () => api.get('/dashboard/projects-health').then(r => r.data).catch(() => []),
  })
  const { data: hoursData } = useQuery({
    queryKey: ['exec-hours', period],
    queryFn: () => api.get('/analytics/hours_by_week', { params: { weeks: 8 } })
      .then(r => r.data).catch(() => []),
  })
  const { data: pipeline = [] } = useQuery({
    queryKey: ['exec-pipeline'],
    queryFn: () => api.get('/pipeline', { params: { page_size: 100 } })
      .then(r => Array.isArray(r.data) ? r.data : (r.data?.items || [])).catch(() => []),
  })
  const { data: profitData = [] } = useQuery({
    queryKey: ['exec-profit'],
    queryFn: () => api.get('/profitability/projects').then(r => r.data).catch(() => []),
  })

  // Calcular KPIs derivados
  const activeProjects = health.length
  const criticalProjects = health.filter(p => p.budget_used_pct > 100 || p.schedule_deviation_days > 0).length
  const onTrackPct = activeProjects > 0
    ? Math.round(((activeProjects - criticalProjects) / activeProjects) * 100) : 0

  const pipelineValue = pipeline.reduce((s, o) => s + (o.expected_revenue || 0), 0)
  const weightedPipeline = pipeline.reduce((s, o) => s + (o.weighted_revenue || 0), 0)
  const wonDeals = pipeline.filter(o => o.stage === 'won').length

  const totalBudget = kpis?.total_budget || 0
  const totalSpent  = kpis?.total_spent  || 0
  const budgetPct = totalBudget > 0 ? Math.round((totalSpent / totalBudget) * 100) : 0

  // Pipeline por etapa
  const STAGES = ['lead','qualified','proposal','negotiation','won','lost']
  const STAGE_LABELS = {lead:'Lead',qualified:'Calificado',proposal:'Propuesta',
    negotiation:'Negociación',won:'Ganado',lost:'Perdido'}
  const pipelineByStage = STAGES.map(s => ({
    name: STAGE_LABELS[s] || s,
    value: pipeline.filter(o => o.stage === s).length,
    revenue: pipeline.filter(o => o.stage === s).reduce((acc,o) => acc+(o.expected_revenue||0),0),
  })).filter(s => s.value > 0)

  // Top proyectos por rentabilidad
  const topProjects = [...profitData]
    .sort((a,b) => (b.margin_pct||0) - (a.margin_pct||0))
    .slice(0, 5)

  // Health distribution for pie
  const healthPie = [
    { name:'En tiempo', value: health.filter(p => !p.schedule_deviation_days && p.budget_used_pct <= 80 && !p.alerts_count).length },
    { name:'En riesgo', value: health.filter(p => p.budget_used_pct > 80 || p.alerts_count > 0).length },
    { name:'Crítico',   value: health.filter(p => p.schedule_deviation_days > 0 || p.budget_used_pct > 100).length },
  ].filter(d => d.value > 0)
  const healthColors = ['#1d9e75','#ef9f27','#e24b4a']

  return (
    <div style={{ padding:32 }}>
      {(kpisLoading || healthLoading) && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0' }}>
          <Spinner />
        </div>
      )}
      <PageHeader
        title="Dashboard Ejecutivo"
        subtitle="Vista C-Level — métricas estratégicas en tiempo real"
        actions={
          <div style={{ display:'flex', gap:8, alignItems:'center' }}>
            <span style={{ fontSize:11, color:'var(--text-2)' }}>Actualizado hace 30s</span>
          </div>
        }
      />

      {/* KPI Row */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(180px, 1fr))', gap:12, marginBottom:24 }}>
        <KpiCard icon="⬡" label="Proyectos activos" value={activeProjects}
          sub={`${onTrackPct}% en tiempo`} color="var(--accent)" />
        <KpiCard icon="💰" label="Presupuesto consumido" value={`${budgetPct}%`}
          sub={`${fmtCurrency(totalSpent)} / ${fmtCurrency(totalBudget)}`}
          color={budgetPct > 90 ? 'var(--danger)' : budgetPct > 75 ? 'var(--warning)' : 'var(--success)'} />
        <KpiCard icon="⏱" label="Horas esta semana" value={kpis?.hours_logged_this_week?.toFixed(0) || 0}
          sub="horas imputadas" color="var(--purple)" />
        <KpiCard icon="🎪" label="Pipeline total" value={fmtCurrency(pipelineValue)}
          sub={`${pipeline.length} oportunidades`} color="var(--warning)" />
        <KpiCard icon="🎫" label="Tickets abiertos" value={kpis?.tasks_open || 0}
          sub={`${kpis?.tasks_overdue || 0} vencidas`} color="var(--text-1)" />
      </div>

      {/* Fila media: health pie + pipeline por etapa + utilización */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 2fr 1fr', gap:16, marginBottom:16 }}>
        {/* Salud proyectos */}
        <div style={panel}>
          <div style={{ fontSize:14, fontWeight:700, marginBottom:16 }}>⬡ Salud proyectos</div>
          {health.length === 0 ? (
            <div style={{ fontSize:12, color:'var(--text-3)', textAlign:'center', padding:20 }}>Sin datos</div>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={140}>
                <PieChart>
                  <Pie data={healthPie} cx="50%" cy="50%" innerRadius={40} outerRadius={60}
                    paddingAngle={3} dataKey="value">
                    {healthPie.map((_, i) => <Cell key={i} fill={healthColors[i % healthColors.length]} />)}
                  </Pie>
                  <Tooltip formatter={(v, n) => [v, n]} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display:'flex', flexDirection:'column', gap:4, marginTop:8 }}>
                {healthPie.map((d, i) => (
                  <div key={d.name} style={{ display:'flex', alignItems:'center', gap:8, fontSize:12 }}>
                    <div style={{ width:8, height:8, borderRadius:'50%',
                      background:healthColors[i], flexShrink:0 }} />
                    <span style={{ flex:1, color:'var(--text-2)' }}>{d.name}</span>
                    <span style={{ fontWeight:700, color:healthColors[i],
                      fontFamily:"'Space Mono',monospace" }}>{d.value}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Pipeline por etapa */}
        <div style={panel}>
          <div style={{ fontSize:14, fontWeight:700, marginBottom:16 }}>🎪 Pipeline de ventas</div>
          <div style={{ display:'flex', gap:16, marginBottom:12 }}>
            <div>
              <div style={{ fontSize:22, fontWeight:900, color:'var(--warning)',
                fontFamily:"'Space Mono',monospace" }}>{fmtCurrency(weightedPipeline)}</div>
              <div style={{ fontSize:11, color:'var(--text-2)' }}>valor ponderado</div>
            </div>
            <div>
              <div style={{ fontSize:22, fontWeight:900, color:'var(--success)',
                fontFamily:"'Space Mono',monospace" }}>{wonDeals}</div>
              <div style={{ fontSize:11, color:'var(--text-2)' }}>ganados</div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={pipelineByStage} margin={{ top:0, right:10, left:-20, bottom:0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" />
              <XAxis dataKey="name" tick={{ fill:'var(--text-3)', fontSize:10 }} />
              <YAxis tick={{ fill:'var(--text-3)', fontSize:10 }} />
              <Tooltip
                contentStyle={{ background:'var(--surface-1)', border:'1px solid #1e2d45', borderRadius:8 }}
                formatter={(v,n) => n === 'revenue' ? [fmtCurrency(v),'Revenue'] : [v,'Deals']} />
              <Bar dataKey="value" fill="#ef9f27" radius={[4,4,0,0]} name="Deals" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Horas semanales */}
        <div style={panel}>
          <div style={{ fontSize:14, fontWeight:700, marginBottom:16 }}>⏱ Horas imputadas</div>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={Array.isArray(hoursData) ? hoursData.slice(-8) : []}
              margin={{ top:0, right:5, left:-25, bottom:0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" />
              <XAxis dataKey="week" tick={{ fill:'var(--text-3)', fontSize:9 }} />
              <YAxis tick={{ fill:'var(--text-3)', fontSize:9 }} />
              <Tooltip contentStyle={{ background:'var(--surface-1)', border:'1px solid #1e2d45', borderRadius:8 }}
                formatter={v => [`${v}h`, 'Horas']} />
              <Area type="monotone" dataKey="hours" stroke="#00d4ff"
                fill="rgba(0,212,255,0.15)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Fila inferior: top rentabilidad + lista proyectos críticos */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
        {/* Top proyectos por margen */}
        <div style={panel}>
          <div style={{ fontSize:14, fontWeight:700, marginBottom:14 }}>💰 Top proyectos por margen</div>
          {topProjects.length === 0 ? (
            <div style={{ fontSize:12, color:'var(--text-3)' }}>Sin datos de rentabilidad</div>
          ) : topProjects.map((p, i) => (
            <div key={p.project_id || i} style={{ display:'flex', alignItems:'center', gap:10,
              padding:'8px 0', borderBottom:'1px solid #1e2d4540' }}>
              <span style={{ fontSize:18, fontWeight:900, color:'var(--text-3)',
                fontFamily:"'Space Mono',monospace", minWidth:20 }}>#{i+1}</span>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ fontSize:13, fontWeight:600,
                  overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                  {p.project_name || p.code}
                </div>
                <div style={{ fontSize:11, color:'var(--text-2)' }}>
                  {fmtCurrency(p.revenue || p.billed || 0)} facturado
                </div>
              </div>
              <div style={{ fontSize:14, fontWeight:800, textAlign:'right',
                color: (p.margin_pct||0) >= 30 ? 'var(--success)' : (p.margin_pct||0) >= 15 ? 'var(--warning)' : 'var(--danger)',
                fontFamily:"'Space Mono',monospace" }}>
                {p.margin_pct ? `${p.margin_pct.toFixed(1)}%` : '—'}
              </div>
            </div>
          ))}
        </div>

        {/* Proyectos que necesitan atención */}
        <div style={panel}>
          <div style={{ fontSize:14, fontWeight:700, marginBottom:14 }}>🚨 Requieren atención</div>
          {health.filter(p => p.schedule_deviation_days > 0 || p.budget_used_pct > 80 || p.alerts_count > 0)
            .slice(0, 6).length === 0 ? (
            <div style={{ fontSize:12, color:'var(--success)', padding:'20px 0', textAlign:'center' }}>
              ✅ Todos los proyectos están en tiempo y presupuesto
            </div>
          ) : (
            health.filter(p => p.schedule_deviation_days > 0 || p.budget_used_pct > 80 || p.alerts_count > 0)
              .slice(0, 6).map(p => {
                const isCrit = p.schedule_deviation_days > 0 || p.budget_used_pct > 100
                return (
                  <div key={p.project_id} style={{ display:'flex', alignItems:'center', gap:10,
                    padding:'8px 0', borderBottom:'1px solid #1e2d4540' }}>
                    <span>{isCrit ? '🔴' : '🟡'}</span>
                    <div style={{ flex:1, minWidth:0 }}>
                      <div style={{ fontSize:13, fontWeight:600,
                        overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                        {p.project_code} — {p.project_name}
                      </div>
                      <div style={{ fontSize:11, color:'var(--text-2)' }}>
                        {p.schedule_deviation_days > 0
                          ? `${p.schedule_deviation_days}d de retraso`
                          : `${p.budget_used_pct?.toFixed(0)}% presupuesto`}
                      </div>
                    </div>
                    <div style={{ textAlign:'right' }}>
                      <div style={{ height:4, width:60, background:'var(--surface-4)', borderRadius:2 }}>
                        <div style={{ width:`${Math.min(100, p.budget_used_pct||0)}%`, height:'100%',
                          background: isCrit ? 'var(--danger)' : 'var(--warning)', borderRadius:2 }} />
                      </div>
                      <div style={{ fontSize:10, color:'var(--text-3)', marginTop:2 }}>
                        {(p.budget_used_pct||0).toFixed(0)}%
                      </div>
                    </div>
                  </div>
                )
              })
          )}
        </div>
      </div>
    </div>
  )
}
