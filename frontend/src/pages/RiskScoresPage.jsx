/**
 * RiskScoresPage — Predicción de riesgo por proyecto
 * Motor basado en señales observables: schedule, budget, scope, recursos
 */
import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { predictionsApi } from '../services/api'
import { Spinner, EmptyState, Button } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AlertOctagon, Brain } from 'lucide-react'
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer, Tooltip } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'

const LEVEL_CFG = {
  low:      { color:'var(--success)', bg:'var(--success-bg)', border:'rgba(52,211,153,0.25)', label:'Bajo', icon:'🟢' },
  medium:   { color:'var(--warning)', bg:'var(--warning-bg)', border:'rgba(251,191,36,0.25)', label:'Medio', icon:'🟡' },
  high:     { color:'var(--danger)',  bg:'var(--danger-bg)',  border:'rgba(239,68,68,0.25)',  label:'Alto', icon:'🔴' },
  critical: { color:'var(--danger)',  bg:'var(--danger-bg)',  border:'rgba(239,68,68,0.25)',  label:'Crítico', icon:'🚨' },
}

function ScoreBar({ value, label, _color }) {
  return (
    <div style={{ marginBottom:10 }}>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4, fontSize: "var(--text-sm)" }}>
        <span style={{ color:'var(--text-2)' }}>{label}</span>
        <span style={{ fontWeight:500, color: value >= 75 ? 'var(--danger)' : value >= 50 ? 'var(--warning)' : 'var(--success)' }}>{Math.round(value)}%</span>
      </div>
      <div style={{ height:6, background:'var(--surface-2)', borderRadius:3, overflow:'hidden' }}>
        <div style={{ height:'100%', borderRadius:3, width:`${Math.min(value,100)}%`, background: value >= 75 ? 'var(--danger)' : value >= 50 ? 'var(--warning)' : 'var(--success)', transition:'width .4s' }} />
      </div>
    </div>
  )
}

const ML_RISK_CFG = {
  low:      { color: 'var(--success)', label: 'Bajo',     bg: 'var(--success-bg)' },
  medium:   { color: 'var(--warning)', label: 'Moderado', bg: 'rgba(250,199,117,0.15)' },
  high:     { color: '#F87171',        label: 'Alto',     bg: 'rgba(248,113,113,0.12)' },
  critical: { color: 'var(--danger)',        label: 'Crítico',  bg: 'rgba(239,68,68,0.15)' },
}

function MLPredictionsTab() {
  const toast = useToast()
  const qc = useQueryClient()

  const { data: portfolio, isLoading: lPortfolio } = useQuery({
    queryKey: ['ml-portfolio-risk'],
    queryFn: () => predictionsApi.portfolioRisk().then(r => r.data),
    retry: 1,
  })
  const { data: models = [], isLoading: lModels } = useQuery({
    queryKey: ['ml-models'],
    queryFn: () => predictionsApi.models().then(r => r.data).catch(() => []),
  })
  const { data: logs = [], isLoading: lLogs } = useQuery({
    queryKey: ['ml-logs'],
    queryFn: () => predictionsApi.logs({ limit: 30 }).then(r => r.data).catch(() => []),
  })
  const { mutate: train, isPending: training } = useMutation({
    mutationFn: () => predictionsApi.train(),
    onSuccess: (res) => {
      qc.invalidateQueries(['ml-models'])
      const d = res.data
      toast.success(d.message || `Modelo entrenado: ${d.samples_used || 0} muestras`)
    },
    onError: e => toast.error(extractErr(e, 'Error al entrenar el modelo')),
  })

  const projects = portfolio?.projects || []
  const summary  = portfolio?.summary  || {}

  return (
    <div>
      {/* Portfolio KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Proyectos analizados', value: summary.total || 0, icon: '🔍' },
          { label: 'Alto / Crítico',       value: (summary.high || 0) + (summary.critical || 0), icon: '🔴', color: 'var(--danger)' },
          { label: 'Riesgo moderado',      value: summary.medium || 0, icon: '🟡', color: 'var(--warning)' },
          { label: 'Bajo riesgo',          value: summary.low || 0,    icon: '🟢', color: 'var(--success)' },
        ].map((k, i) => (
          <div key={i} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ fontSize: "var(--text-lg-em)", marginBottom: 4 }}>{k.icon}</div>
            <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 700, color: k.color || 'var(--text-1)' }}>{k.value}</div>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{k.label}</div>
          </div>
        ))}
      </div>

      {/* Projects risk list */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 16, alignItems: 'flex-start' }}>
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
            Cartera de proyectos — ML
          </div>
          {lPortfolio ? <div style={{ padding: 24 }}><Spinner /></div> : projects.length === 0 ? (
            <EmptyState icon="🤖" title="Sin predicciones ML" description="Entrena el modelo primero para ver predicciones de riesgo" />
          ) : (
            <div style={{ maxHeight: 480, overflowY: 'auto' }}>
              {projects.map(p => {
                const cfg = ML_RISK_CFG[p.risk_level] || ML_RISK_CFG.low
                return (
                  <div key={p.project_id} style={{ padding: '12px 18px', borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', gap: 14 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: cfg.color, flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: "var(--text-base)", fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.project_name}</div>
                      {p.recommendation && (
                        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 2 }}>💡 {p.recommendation}</div>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexShrink: 0 }}>
                      {p.cpi != null && <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>CPI {p.cpi?.toFixed(2)}</span>}
                      {p.spi != null && <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>SPI {p.spi?.toFixed(2)}</span>}
                      <span style={{ fontSize: "var(--text-xs)", padding: '2px 8px', borderRadius: 20, background: cfg.bg, color: cfg.color, fontWeight: 500 }}>{cfg.label}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Right panel: models + training + logs */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Train */}
          <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '16px 18px' }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 600, marginBottom: 8 }}>Entrenar modelo</div>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 12 }}>
              Usa el historial de proyectos cerrados para entrenar el modelo de predicción de sobrecosto/retraso.
            </div>
            <Button onClick={() => train()} disabled={training} style={{ width: '100%' }}>
              <Brain size={13} style={{ marginRight: 6 }} />
              {training ? 'Entrenando...' : 'Entrenar ahora'}
            </Button>
          </div>

          {/* Models */}
          <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
            <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
              Versiones del modelo
            </div>
            <div style={{ maxHeight: 180, overflowY: 'auto' }}>
              {lModels ? <div style={{ padding: 16 }}><Spinner /></div> : models.length === 0 ? (
                <div style={{ padding: '20px 16px', textAlign: 'center', fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>Sin modelos entrenados</div>
              ) : models.map((m, i) => (
                <div key={m.id || i} style={{ padding: '8px 16px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-sm)" }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: 500 }}>v{m.version || i + 1}</span>
                    {m.is_active && <span style={{ fontSize: "var(--text-2xs)", padding: '1px 6px', borderRadius: 4, background: 'var(--accent-muted)', color: 'var(--accent)' }}>Activo</span>}
                  </div>
                  <div style={{ color: 'var(--text-3)', marginTop: 2 }}>
                    {m.samples_used || 0} muestras · {m.trained_at?.slice(0, 10) || ''}
                    {m.accuracy_score != null && <span> · AUC {m.accuracy_score.toFixed(2)}</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Logs */}
          <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
            <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
              Historial de predicciones
            </div>
            <div style={{ maxHeight: 200, overflowY: 'auto' }}>
              {lLogs ? <div style={{ padding: 16 }}><Spinner /></div> : logs.length === 0 ? (
                <div style={{ padding: '20px 16px', textAlign: 'center', fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>Sin predicciones registradas</div>
              ) : logs.map((l, i) => {
                const cfg = ML_RISK_CFG[l.risk_level] || ML_RISK_CFG.low
                return (
                  <div key={l.id || i} style={{ padding: '8px 16px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-xs)" }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 150, fontWeight: 500 }}>{l.project_name || l.project_id}</span>
                      <span style={{ color: cfg.color, fontWeight: 500, flexShrink: 0 }}>{cfg.label}</span>
                    </div>
                    <div style={{ color: 'var(--text-3)', marginTop: 2 }}>{l.predicted_at?.slice(0, 16) || ''}</div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function RiskScoresPage() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [tab, setTab] = useState('rules')
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
    <PageShell>
      <PageHeader
        icon={<AlertOctagon size={18} />}
        title={t('risk_scores.title')}
        subtitle={t('risk_scores.subtitle')}
        showListExport={tab === 'rules' && filtered.length > 0}
        exportTargetSelector='[data-export-table="risk-scores-list"]'
        exportFilePrefix='risk_scores'
      />

      {/* Tab nav */}
      <div style={{ display:'flex', gap:4, marginBottom:24, borderBottom:'1px solid var(--surface-4)', paddingBottom:0 }}>
        {[['rules','🛡️ Riesgo basado en señales'],['ml','🤖 Predicciones ML']].map(([id,label]) => (
          <button key={id} onClick={() => setTab(id)}
            style={{ padding:'8px 18px', fontSize: "var(--text-base)", fontWeight: tab===id ? 700 : 400,
              color: tab===id ? 'var(--accent)' : 'var(--text-2)', background:'transparent',
              border:'none', borderBottom: tab===id ? '2px solid var(--accent)' : '2px solid transparent',
              cursor:'pointer', fontFamily:'inherit', transition:'color .15s' }}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'ml' && <MLPredictionsTab />}

      {tab === 'rules' && <>
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
            <button key={s.level} type="button"
              onClick={() => setFilterLevel(filterLevel === s.level ? 'all' : s.level)}
              style={{ background:cfg.bg, border:`.5px solid ${cfg.border}`, borderRadius:10, padding:'16px 18px', cursor:'pointer', opacity: filterLevel !== 'all' && filterLevel !== s.level ? 0.5 : 1, textAlign:'left', fontFamily:'inherit' }}>
              <div style={{ fontSize: "var(--text-2xl)", marginBottom:4 }}>{cfg.icon}</div>
              <div style={{ fontSize: "var(--text-2xl-em)", fontWeight:500, color:cfg.color }}>{s.count}</div>
              <div style={{ fontSize: "var(--text-sm)", color:cfg.color }}>Riesgo {s.label}</div>
            </button>
          )
        })}
      </div>

      <div style={{ display:'flex', gap:12, marginBottom:20, alignItems:'center' }}>
        {filterLevel !== 'all' && (
          <button onClick={() => setFilterLevel('all')}
            style={{ background:'transparent', border:'.5px solid var(--surface-4)', borderRadius:6, padding:'5px 12px', color:'var(--text-2)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit' }}>
            × Quitar filtro
          </button>
        )}
        <button onClick={() => refresh()}
          style={{ marginLeft:'auto', background:'transparent', border:'.5px solid var(--surface-4)', borderRadius:6, padding:'6px 14px', color:'var(--text-2)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit' }}>
          {refreshing || isFetching ? '↻ Recalculando...' : '↻ Recalcular todo'}
        </button>
      </div>

      <div style={{ display:'grid', gridTemplateColumns: selected ? '1fr 360px' : '1fr', gap:20 }}>
        {/* Lista de proyectos */}
        <div>
          {isLoading ? <Spinner /> : filtered.length === 0 ? (
            <EmptyState icon="🛡" title="Sin datos de riesgo" description="Los proyectos con calculos de riesgo apareceran aqui" />
          ) : (
            <div data-export-table="risk-scores-list" style={{ display:'flex', flexDirection:'column', gap:8 }}>
              {filtered.map(p => {
                const cfg = LEVEL_CFG[p.level] || LEVEL_CFG.low
                const isSelected = selected === p.project_id
                return (
                  <button key={p.project_id} type="button"
                    onClick={() => setSelected(isSelected ? null : p.project_id)}
                    style={{ background:'var(--surface-1)', border:`.5px solid ${isSelected ? cfg.border : 'var(--surface-4)'}`, borderRadius:10, padding:'14px 18px', cursor:'pointer', transition:'border-color .2s', width:'100%', textAlign:'left', fontFamily:'inherit' }}>
                    <div style={{ display:'flex', alignItems:'center', gap:12 }}>
                      <span style={{ fontSize: "var(--text-xl)" }}>{cfg.icon}</span>
                      <div style={{ flex:1 }}>
                        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:4 }}>
                          <div>
                            <span style={{ fontSize: "var(--text-base)", fontWeight:500, marginRight:8 }}>{p.project_name}</span>
                            <span style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', padding:'1px 6px', borderRadius:4, background:'var(--surface-2)' }}>{p.project_code}</span>
                          </div>
                          <div style={{ display:'flex', gap:10, alignItems:'center' }}>
                            <span style={{ fontSize: "var(--text-xs)", padding:'2px 8px', borderRadius:5, background:cfg.bg, color:cfg.color, fontWeight:500 }}>{cfg.label}</span>
                            <span style={{ fontSize: "var(--text-lg-em)", fontWeight:700, color:cfg.color }}>{Math.round(p.overall_score || 0)}</span>
                            <span style={{ fontSize: "var(--text-xs)", color:'var(--text-3)' }}>/100</span>
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
                              <div style={{ fontSize: "var(--text-2xs)", color:'var(--text-3)', marginBottom:2 }}>{item.label}</div>
                              <div style={{ height:4, background:'var(--surface-2)', borderRadius:2, overflow:'hidden' }}>
                                <div style={{ height:'100%', borderRadius:2, width:`${Math.min(item.val||0,100)}%`, background: (item.val||0) >= 75 ? 'var(--danger)' : (item.val||0) >= 50 ? 'var(--warning)' : 'var(--success)' }} />
                              </div>
                              <div style={{ fontSize: "var(--text-2xs)", color:'var(--text-2)', marginTop:1 }}>{Math.round(item.val||0)}%</div>
                            </div>
                          ))}
                        </div>
                        {p.recommendation && (
                          <div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', fontStyle:'italic' }}>💡 {p.recommendation}</div>
                        )}
                      </div>
                    </div>
                    {p.delay_probability_pct > 20 && (
                      <div style={{ marginTop:8, display:'flex', gap:16, paddingTop:8, borderTop:`.5px solid var(--surface-4)`, fontSize: "var(--text-sm)" }}>
                        <span>Prob. retraso: <strong style={{ color:'var(--danger)' }}>{Math.round(p.delay_probability_pct)}%</strong></span>
                        {p.predicted_delay_weeks && (
                          <span>Retraso estimado: <strong style={{ color:'var(--warning)' }}>{p.predicted_delay_weeks}sem</strong></span>
                        )}
                        <span style={{ color:'var(--text-3)' }}>Calc: {p.computed_at}</span>
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Panel detalle */}
        {selected && detail && (
          <div style={{ background:'var(--surface-1)', border:'.5px solid var(--surface-4)', borderRadius:12, padding:'20px 22px', position:'sticky', top:80, alignSelf:'start' }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
              <div style={{ fontSize: "var(--text-md)", fontWeight:500 }}>{detail.project_name}</div>
              <button onClick={() => setSelected(null)} style={{ background:'transparent', border:'none', cursor:'pointer', fontSize: "var(--text-lg-em)", color:'var(--text-3)', lineHeight:1 }}>×</button>
            </div>

            {/* Radar chart */}
            <ResponsiveContainer width="100%" height={200}>
              <RadarChart data={radarData}>
                <PolarGrid stroke="var(--surface-4)" />
                <PolarAngleAxis dataKey="subject" tick={{ fontSize: "var(--text-xs)", fill:'var(--text-2)' }} />
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

            <div style={{ marginTop:16, background:'var(--surface-2)', borderRadius:8, padding:'12px 14px' }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight:500, color:'var(--text-2)', marginBottom:6, textTransform:'uppercase', letterSpacing:'.06em' }}>Recomendación</div>
              <div style={{ fontSize: "var(--text-sm)", color:'var(--text-1)' }}>{detail.recommendation}</div>
            </div>

            {(detail.delay_probability_pct > 0) && (
              <div style={{ marginTop:12, display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
                <div style={{ background:'var(--danger-bg)', borderRadius:8, padding:'10px 12px', textAlign:'center' }}>
                  <div style={{ fontSize: "var(--text-lg-em)", fontWeight:600, color:'var(--danger)' }}>{Math.round(detail.delay_probability_pct)}%</div>
                  <div style={{ fontSize: "var(--text-2xs)", color:'var(--danger)' }}>Prob. retraso</div>
                </div>
                <div style={{ background:'var(--warning-bg)', borderRadius:8, padding:'10px 12px', textAlign:'center' }}>
                  <div style={{ fontSize: "var(--text-lg-em)", fontWeight:600, color:'var(--warning)' }}>{detail.predicted_delay_weeks || 0} sem</div>
                  <div style={{ fontSize: "var(--text-2xs)", color:'var(--warning)' }}>Retraso previsto</div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      </>}
    </PageShell>
  )
}
