/**
 * RiskScoresPage — Predicción de riesgo por proyecto
 * Motor basado en señales observables: schedule, budget, scope, recursos
 */
import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer, Tooltip } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'

const LEVEL_CFG = {
  low:      { color:'var(--color-text-success)', bg:'var(--color-background-success)', border:'var(--color-border-success)', label:'Bajo', icon:'🟢' },
  medium:   { color:'var(--color-text-warning)', bg:'var(--color-background-warning)', border:'var(--color-border-warning)', label:'Medio', icon:'🟡' },
  high:     { color:'var(--color-text-danger)',  bg:'var(--color-background-danger)',  border:'var(--color-border-danger)',  label:'Alto', icon:'🔴' },
  critical: { color:'var(--color-text-danger)',  bg:'var(--color-background-danger)',  border:'var(--color-border-danger)',  label:'Crítico', icon:'🚨' },
}

function ScoreBar({ value, label, _color }) {
  return (
    <div style={{ marginBottom:10 }}>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4, fontSize:12 }}>
        <span style={{ color:'var(--color-text-secondary)' }}>{label}</span>
        <span style={{ fontWeight:500, color: value >= 75 ? 'var(--color-text-danger)' : value >= 50 ? 'var(--color-text-warning)' : 'var(--color-text-success)' }}>{Math.round(value)}%</span>
      </div>
      <div style={{ height:6, background:'var(--color-background-secondary)', borderRadius:3, overflow:'hidden' }}>
        <div style={{ height:'100%', borderRadius:3, width:`${Math.min(value,100)}%`, background: value >= 75 ? 'var(--danger)' : value >= 50 ? 'var(--warning)' : 'var(--success)', transition:'width .4s' }} />
      </div>
    </div>
  )
}

export default function RiskScoresPage() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [selected, setSelected] = useState(null)
  const [filterLevel, setFilterLevel] = useState('all')

  const { data: response, isLoading, isFetching } = useQuery({
    queryKey: ['risk-scores'],
    queryFn: () => api.get('/risk-scores').then(r => r.data),
  })
  const { data: detail } = useQuery({
    queryKey: ['risk-detail', selected],
    queryFn: () => api.get(`/risk-scores/${selected}`).then(r => r.data),
    enabled: !!selected,
  })
  const { mutate: refresh, isPending:refreshing } = useMutation({
    mutationFn: () => api.get('/risk-scores?refresh=true').then(r=>r.data),
    onSuccess: () => qc.invalidateQueries(['risk-scores']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const projects = response?.projects || []
  const summary = response?.summary || {}

  const filtered = filterLevel === 'all' ? projects : projects.filter(p => p.level === filterLevel)

  const radarData = detail ? [
    { subject:'Cronograma', A: Math.round(detail.schedule_risk || 0) },
    { subject:'Presupuesto', A: Math.round(detail.budget_risk || 0) },
    { subject:'Alcance', A: Math.round(detail.scope_risk || 0) },
    { subject:'Recursos', A: Math.round(detail.resource_risk || 0) },
  ] : []

  return (
    <div style={{ padding:32 }}>
      <PageHeader title={t('risk_scores.title')} subtitle={t('risk_scores.subtitle')} />

      {/* Summary KPIs */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:14, marginBottom:28 }}>
        {[
          { level:'critical', label:'Crítico', count: summary.critical || 0 },
          { level:'high',     label:'Alto',    count: summary.high || 0 },
          { level:'medium',   label:'Medio',   count: summary.medium || 0 },
          { level:'low',      label:'Bajo',    count: summary.low || 0 },
        ].map(s => {
          const cfg = LEVEL_CFG[s.level]
          return (
            <div key={s.level}
              onClick={() => setFilterLevel(filterLevel === s.level ? 'all' : s.level)}
              style={{ background:cfg.bg, border:`.5px solid ${cfg.border}`, borderRadius:10, padding:'16px 18px', cursor:'pointer', opacity: filterLevel !== 'all' && filterLevel !== s.level ? 0.5 : 1 }}>
              <div style={{ fontSize:24, marginBottom:4 }}>{cfg.icon}</div>
              <div style={{ fontSize:26, fontWeight:500, color:cfg.color }}>{s.count}</div>
              <div style={{ fontSize:12, color:cfg.color }}>Riesgo {s.label}</div>
            </div>
          )
        })}
      </div>

      <div style={{ display:'flex', gap:12, marginBottom:20, alignItems:'center' }}>
        {filterLevel !== 'all' && (
          <button onClick={() => setFilterLevel('all')}
            style={{ background:'transparent', border:'.5px solid var(--color-border-secondary)', borderRadius:6, padding:'5px 12px', color:'var(--color-text-secondary)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
            × Quitar filtro
          </button>
        )}
        <button onClick={() => refresh()}
          style={{ marginLeft:'auto', background:'transparent', border:'.5px solid var(--color-border-secondary)', borderRadius:6, padding:'6px 14px', color:'var(--color-text-secondary)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
          {refreshing || isFetching ? '↻ Recalculando...' : '↻ Recalcular todo'}
        </button>
      </div>

      <div style={{ display:'grid', gridTemplateColumns: selected ? '1fr 360px' : '1fr', gap:20 }}>
        {/* Lista de proyectos */}
        <div>
          {isLoading ? <Spinner /> : filtered.length === 0 ? (
            <EmptyState icon="🛡" title="Sin datos de riesgo" description="Los proyectos con calculos de riesgo apareceran aqui" />
          ) : (
            <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
              {filtered.map(p => {
                const cfg = LEVEL_CFG[p.level] || LEVEL_CFG.low
                const isSelected = selected === p.project_id
                return (
                  <div key={p.project_id}
                    onClick={() => setSelected(isSelected ? null : p.project_id)}
                    style={{ background:'var(--color-background-primary)', border:`.5px solid ${isSelected ? cfg.border : 'var(--color-border-tertiary)'}`, borderRadius:10, padding:'14px 18px', cursor:'pointer', transition:'border-color .2s' }}>
                    <div style={{ display:'flex', alignItems:'center', gap:12 }}>
                      <span style={{ fontSize:20 }}>{cfg.icon}</span>
                      <div style={{ flex:1 }}>
                        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:4 }}>
                          <div>
                            <span style={{ fontSize:13, fontWeight:500, marginRight:8 }}>{p.project_name}</span>
                            <span style={{ fontSize:11, color:'var(--color-text-secondary)', padding:'1px 6px', borderRadius:4, background:'var(--color-background-secondary)' }}>{p.project_code}</span>
                          </div>
                          <div style={{ display:'flex', gap:10, alignItems:'center' }}>
                            <span style={{ fontSize:11, padding:'2px 8px', borderRadius:5, background:cfg.bg, color:cfg.color, fontWeight:500 }}>{cfg.label}</span>
                            <span style={{ fontSize:18, fontWeight:700, color:cfg.color }}>{Math.round(p.overall_score || 0)}</span>
                            <span style={{ fontSize:11, color:'var(--color-text-tertiary)' }}>/100</span>
                          </div>
                        </div>
                        <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:8, marginBottom:8 }}>
                          {[
                            { label:'Cronograma', val: p.schedule_risk },
                            { label:'Presupuesto', val: p.budget_risk },
                            { label:'Alcance', val: p.scope_risk },
                            { label:'Recursos', val: p.resource_risk },
                          ].map(item => (
                            <div key={item.label}>
                              <div style={{ fontSize:10, color:'var(--color-text-tertiary)', marginBottom:2 }}>{item.label}</div>
                              <div style={{ height:4, background:'var(--color-background-secondary)', borderRadius:2, overflow:'hidden' }}>
                                <div style={{ height:'100%', borderRadius:2, width:`${Math.min(item.val||0,100)}%`, background: (item.val||0) >= 75 ? 'var(--danger)' : (item.val||0) >= 50 ? 'var(--warning)' : 'var(--success)' }} />
                              </div>
                              <div style={{ fontSize:10, color:'var(--color-text-secondary)', marginTop:1 }}>{Math.round(item.val||0)}%</div>
                            </div>
                          ))}
                        </div>
                        {p.recommendation && (
                          <div style={{ fontSize:11, color:'var(--color-text-secondary)', fontStyle:'italic' }}>💡 {p.recommendation}</div>
                        )}
                      </div>
                    </div>
                    {p.delay_probability_pct > 20 && (
                      <div style={{ marginTop:8, display:'flex', gap:16, paddingTop:8, borderTop:`.5px solid var(--color-border-tertiary)`, fontSize:12 }}>
                        <span>Prob. retraso: <strong style={{ color:'var(--color-text-danger)' }}>{Math.round(p.delay_probability_pct)}%</strong></span>
                        {p.predicted_delay_weeks && (
                          <span>Retraso estimado: <strong style={{ color:'var(--color-text-warning)' }}>{p.predicted_delay_weeks}sem</strong></span>
                        )}
                        <span style={{ color:'var(--color-text-tertiary)' }}>Calc: {p.computed_at}</span>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Panel detalle */}
        {selected && detail && (
          <div style={{ background:'var(--color-background-primary)', border:'.5px solid var(--color-border-secondary)', borderRadius:12, padding:'20px 22px', position:'sticky', top:80, alignSelf:'start' }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
              <div style={{ fontSize:14, fontWeight:500 }}>{detail.project_name}</div>
              <button onClick={() => setSelected(null)} style={{ background:'transparent', border:'none', cursor:'pointer', fontSize:18, color:'var(--color-text-tertiary)', lineHeight:1 }}>×</button>
            </div>

            {/* Radar chart */}
            <ResponsiveContainer width="100%" height={200}>
              <RadarChart data={radarData}>
                <PolarGrid stroke="var(--color-border-tertiary)" />
                <PolarAngleAxis dataKey="subject" tick={{ fontSize:11, fill:'var(--color-text-secondary)' }} />
                <Radar name={detail.project_name} dataKey="A" stroke="#3266AD" fill="#3266AD" fillOpacity={0.25} />
                <Tooltip formatter={v => [`${Math.round(v)}%`, 'Riesgo']} />
              </RadarChart>
            </ResponsiveContainer>

            <div style={{ marginTop:16 }}>
              <ScoreBar value={detail.schedule_risk || 0} label="Riesgo de cronograma" />
              <ScoreBar value={detail.budget_risk || 0} label="Riesgo de presupuesto" />
              <ScoreBar value={detail.scope_risk || 0} label="Riesgo de alcance" />
              <ScoreBar value={detail.resource_risk || 0} label="Riesgo de recursos" />
            </div>

            <div style={{ marginTop:16, background:'var(--color-background-secondary)', borderRadius:8, padding:'12px 14px' }}>
              <div style={{ fontSize:11, fontWeight:500, color:'var(--color-text-secondary)', marginBottom:6, textTransform:'uppercase', letterSpacing:'.06em' }}>Recomendación</div>
              <div style={{ fontSize:12, color:'var(--color-text-primary)' }}>{detail.recommendation}</div>
            </div>

            {(detail.delay_probability_pct > 0) && (
              <div style={{ marginTop:12, display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
                <div style={{ background:'var(--color-background-danger)', borderRadius:8, padding:'10px 12px', textAlign:'center' }}>
                  <div style={{ fontSize:18, fontWeight:600, color:'var(--color-text-danger)' }}>{Math.round(detail.delay_probability_pct)}%</div>
                  <div style={{ fontSize:10, color:'var(--color-text-danger)' }}>Prob. retraso</div>
                </div>
                <div style={{ background:'var(--color-background-warning)', borderRadius:8, padding:'10px 12px', textAlign:'center' }}>
                  <div style={{ fontSize:18, fontWeight:600, color:'var(--color-text-warning)' }}>{detail.predicted_delay_weeks || 0} sem</div>
                  <div style={{ fontSize:10, color:'var(--color-text-warning)' }}>Retraso previsto</div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
