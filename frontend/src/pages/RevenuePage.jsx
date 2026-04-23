/**
 * RevenuePage — Reconocimiento de ingresos ASC 606 / IFRS 15
 * Configura el método por proyecto y registra entradas mensuales
 */
import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { projectsApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { TrendingUp } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'

const fs = { width:'100%', background:'var(--surface-2)', border:'.5px solid var(--surface-4)', borderRadius:8, padding:'9px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:500, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'.07em', display:'block', marginBottom:5 }
const card = { background:'var(--surface-1)', border:'.5px solid var(--surface-4)', borderRadius:12 }

const METHOD_CFG = {
  percentage_complete: { label:'% Completado',        desc:'Reconoce proporcionalmente al avance de tareas', icon:'📊' },
  time_and_material:   { label:'T&M',                 desc:'Reconoce al registrar horas facturables', icon:'⏱' },
  straight_line:       { label:'Línea recta',          desc:'Distribuye el contrato en partes iguales por mes', icon:'📈' },
  milestone:           { label:'Por hito',             desc:'Reconoce al alcanzar hitos acordados', icon:'🎯' },
  completed_contract:  { label:'Contrato completado',  desc:'Solo reconoce al cerrar el proyecto', icon:'✅' },
}

const _LEVEL_CFG = {
  low:      { color:'var(--success)',  bg:'var(--success-bg)',  label:'Bajo' },
  medium:   { color:'var(--warning)',  bg:'var(--warning-bg)',  label:'Medio' },
  high:     { color:'var(--danger)',   bg:'var(--danger-bg)',   label:'Alto' },
  critical: { color:'var(--danger)',   bg:'var(--danger-bg)',   label:'Crítico' },
}

function fmtEur(n) {
  if (!n && n !== 0) return '—'
  return new Intl.NumberFormat('es-ES', { style:'currency', currency:'EUR', minimumFractionDigits:0, maximumFractionDigits:0 }).format(n)
}

export default function RevenuePage() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [tab, setTab] = useState('summary')
  const [showCreate, setShowCreate] = useState(false)
  const [showCompute, setShowCompute] = useState(null)
  const [form, setForm] = useState({ project_id:'', method:'percentage_complete', contract_value:'', start_date:'', end_date:'', notes:'' })
  const [computePeriod, setComputePeriod] = useState(new Date().toISOString().slice(0,7) + '-01')

  const { data: rules = [], isLoading } = useQuery({ queryKey:['rev-rules'], queryFn:() => api.get('/revenue/rules').then(r=>r.data) })
  const { data: summary } = useQuery({ queryKey:['rev-summary'], queryFn:() => api.get('/revenue/summary').then(r=>r.data) })
  const { data: projects = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data || []) })

  const { mutate: createRule, isPending:creating } = useMutation({
    mutationFn: d => api.post('/revenue/rules', d),
    onSuccess: () => { qc.invalidateQueries(['rev-rules']); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: _autoCompute, isPending: _autoComputing } = useMutation({
    mutationFn: () => api.post('/revenue/auto-compute', { period: computePeriod }),
    onSuccess: (res) => {
      qc.invalidateQueries(['revenue-rules'])
      toast.success(`Auto-compute: ${res.data.total_recognised?.toLocaleString('es-ES', {style:'currency',currency:'EUR'})} reconocidos`)
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: compute, isPending:computing } = useMutation({
    mutationFn: ({ id, period }) => api.post(`/revenue/rules/${id}/compute`, { period }),
    onSuccess: () => { qc.invalidateQueries(['rev-rules']); qc.invalidateQueries(['rev-summary']); setShowCompute(null) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const byMonth = summary?.by_month || []
  const chartData = byMonth.slice(-12).map(m => ({
    mes: m.month.slice(0,7),
    Reconocido: Math.round(m.recognised),
    Diferido: Math.round(m.deferred),
  }))

  const TABS = [
    { id:'summary', label:'Resumen' },
    { id:'rules',   label:'Reglas por proyecto' },
    { id:'info',    label:'ASC 606 / IFRS 15' },
  ]

  return (
    <div style={{ padding:32 }}>
      <PageHeader icon={<TrendingUp size={18} />} title={t('profitability.revenue')} subtitle={t('profitability.revenue_subtitle')} />

      {/* KPIs */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:14, marginBottom:28 }}>
        {[
          { label:'Total reconocido', value:fmtEur(summary?.total_recognised), icon:'✅' },
          { label:'Total diferido',   value:fmtEur(summary?.total_deferred),   icon:'⏳' },
          { label:'Proyectos activos', value:rules.length,                      icon:'⬡' },
          { label:'Entradas registradas', value:summary?.entry_count || 0,      icon:'📋' },
        ].map((k,i) => (
          <div key={i} style={{ background:'var(--surface-2)', borderRadius:10, padding:'16px 18px' }}>
            <div style={{ fontSize:20, marginBottom:6 }}>{k.icon}</div>
            <div style={{ fontSize:22, fontWeight:500, marginBottom:2 }}>{k.value}</div>
            <div style={{ fontSize:12, color:'var(--text-2)' }}>{k.label}</div>
          </div>
        ))}
      </div>

      {/* Tab nav */}
      <div style={{ display:'flex', gap:8, marginBottom:24 }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ padding:'8px 16px', borderRadius:8, border:`.5px solid ${tab===t.id?'rgba(0,212,255,0.25)':'var(--surface-4)'}`, background:tab===t.id?'var(--accent-muted)':'transparent', color:tab===t.id?'var(--accent)':'var(--text-2)', fontSize:13, fontWeight:500, cursor:'pointer', fontFamily:'inherit' }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Resumen ── */}
      {tab === 'summary' && (
        <div>
          {chartData.length > 0 ? (
            <div style={{ ...card, padding:'20px 24px' }}>
              <div style={{ fontSize:13, fontWeight:500, marginBottom:16 }}>Ingresos reconocidos vs diferidos por mes</div>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={chartData}>
                  <XAxis dataKey="mes" tick={{ fontSize:11 }} />
                  <YAxis tickFormatter={v => `${Math.round(v/1000)}k€`} tick={{ fontSize:11 }} />
                  <Tooltip formatter={(v,n) => [fmtEur(v), n]} />
                  <Legend />
                  <Bar dataKey="Reconocido" fill="#1D9E75" radius={[3,3,0,0]} />
                  <Bar dataKey="Diferido"   fill="#FAC775" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState icon="📊" title="Sin datos de reconocimiento" description="Crea reglas de reconocimiento de ingresos para ver el grafico" />
          )}
        </div>
      )}

      {/* ── Reglas ── */}
      {tab === 'rules' && (
        <div>
          <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:16 }}>
            <Button onClick={() => setShowCreate(true)}>+ Nueva regla</Button>
          </div>
          {isLoading ? <Spinner /> : rules.length === 0 ? (
            <EmptyState icon="📋" title="Sin reglas de reconocimiento" description="Crea una regla para iniciar el reconocimiento de ingresos" />
          ) : (
            <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
              {rules.map(r => {
                const mCfg = METHOD_CFG[r.method] || { label:r.method, icon:'•', desc:'' }
                const pct = r.contract_value > 0 ? Math.round(r.total_recognised / r.contract_value * 100) : 0
                return (
                  <div key={r.id} style={{ ...card, padding:'16px 20px' }}>
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
                      <div style={{ flex:1 }}>
                        <div style={{ display:'flex', gap:10, alignItems:'center', marginBottom:6 }}>
                          <span style={{ fontSize:14, fontWeight:500 }}>{r.project_name}</span>
                          <span style={{ fontSize:11, color:'var(--text-2)', padding:'1px 6px', borderRadius:4, background:'var(--surface-2)' }}>{r.project_code}</span>
                          <span style={{ fontSize:11, padding:'1px 6px', borderRadius:4, background:'var(--accent-muted)', color:'var(--accent)' }}>{mCfg.icon} {mCfg.label}</span>
                        </div>
                        <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:16, marginBottom:10 }}>
                          <div><div style={{ fontSize:11, color:'var(--text-2)', marginBottom:2 }}>Valor contrato</div><div style={{ fontSize:14, fontWeight:500 }}>{fmtEur(r.contract_value)}</div></div>
                          <div><div style={{ fontSize:11, color:'var(--text-2)', marginBottom:2 }}>Reconocido</div><div style={{ fontSize:14, fontWeight:500, color:'var(--success)' }}>{fmtEur(r.total_recognised)}</div></div>
                          <div><div style={{ fontSize:11, color:'var(--text-2)', marginBottom:2 }}>Diferido</div><div style={{ fontSize:14, fontWeight:500, color:'var(--warning)' }}>{fmtEur(r.total_deferred)}</div></div>
                          <div><div style={{ fontSize:11, color:'var(--text-2)', marginBottom:2 }}>Entradas</div><div style={{ fontSize:14, fontWeight:500 }}>{r.entry_count}</div></div>
                        </div>
                        {r.contract_value > 0 && (
                          <div>
                            <div style={{ height:6, background:'var(--surface-2)', borderRadius:3, overflow:'hidden' }}>
                              <div style={{ height:'100%', background:'var(--success-bg)', width:`${Math.min(pct,100)}%`, borderRadius:3 }} />
                            </div>
                            <div style={{ fontSize:11, color:'var(--text-2)', marginTop:3 }}>{pct}% reconocido</div>
                          </div>
                        )}
                      </div>
                      <div style={{ marginLeft:20 }}>
                        <Button onClick={() => setShowCompute(r)}>Calcular período</Button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Info ASC 606 ── */}
      {tab === 'info' && (
        <div style={{ ...card, padding:'24px 28px', maxWidth:700 }}>
          <div style={{ fontSize:14, fontWeight:500, marginBottom:16 }}>ASC 606 / IFRS 15 — Los 5 pasos</div>
          {[
            ['1. Identificar el contrato', 'Acuerdo con el cliente con términos comerciales claros y probabilidad de cobro.'],
            ['2. Identificar las obligaciones', 'Cada entregable distinto (módulo, fase, servicio) es una obligación de desempeño separada.'],
            ['3. Determinar el precio', 'Precio total del contrato, incluyendo variables, descuentos y opciones.'],
            ['4. Asignar el precio', 'Distribuir el precio entre cada obligación según valor relativo de mercado.'],
            ['5. Reconocer los ingresos', 'Reconocer al satisfacer cada obligación: a lo largo del tiempo o en un momento puntual.'],
          ].map(([title, desc], i) => (
            <div key={i} style={{ display:'flex', gap:14, padding:'12px 0', borderBottom:'.5px solid var(--surface-4)' }}>
              <div style={{ width:28, height:28, borderRadius:'50%', background:'var(--accent-muted)', color:'var(--accent)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:12, fontWeight:700, flexShrink:0 }}>{i+1}</div>
              <div>
                <div style={{ fontSize:13, fontWeight:500, marginBottom:3 }}>{title}</div>
                <div style={{ fontSize:12, color:'var(--text-2)' }}>{desc}</div>
              </div>
            </div>
          ))}
          <div style={{ marginTop:16, display:'flex', flexDirection:'column', gap:10 }}>
            <div style={{ fontSize:13, fontWeight:500 }}>Métodos disponibles en Clarive</div>
            {Object.entries(METHOD_CFG).map(([k, v]) => (
              <div key={k} style={{ display:'flex', gap:10, padding:'8px 12px', background:'var(--surface-2)', borderRadius:8 }}>
                <span style={{ fontSize:16 }}>{v.icon}</span>
                <div>
                  <div style={{ fontSize:12, fontWeight:500 }}>{v.label}</div>
                  <div style={{ fontSize:11, color:'var(--text-2)' }}>{v.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Modal nueva regla */}
      {showCreate && (
        <Modal open title="Nueva regla de reconocimiento" onClose={() => setShowCreate(false)} width={520}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div><label style={ls}>Proyecto</label>
              <select value={form.project_id} onChange={e=>setForm(f=>({...f,project_id:e.target.value}))} style={fs}>
                <option value="">Seleccionar proyecto...</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
              </select>
            </div>
            <div><label style={ls}>Método de reconocimiento</label>
              <select value={form.method} onChange={e=>setForm(f=>({...f,method:e.target.value}))} style={fs}>
                {Object.entries(METHOD_CFG).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label} — {v.desc}</option>)}
              </select>
            </div>
            <div><label style={ls}>Valor del contrato (€)</label>
              <input type="number" value={form.contract_value} onChange={e=>setForm(f=>({...f,contract_value:e.target.value}))} style={fs} placeholder="Ej: 50000" />
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
              <div><label style={ls}>Fecha inicio</label><input type="date" value={form.start_date} onChange={e=>setForm(f=>({...f,start_date:e.target.value}))} style={fs} /></div>
              <div><label style={ls}>Fecha fin</label><input type="date" value={form.end_date} onChange={e=>setForm(f=>({...f,end_date:e.target.value}))} style={fs} /></div>
            </div>
            <div><label style={ls}>Notas</label>
              <textarea value={form.notes} onChange={e=>setForm(f=>({...f,notes:e.target.value}))} rows={2} style={{...fs,resize:'vertical'}} />
            </div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
              <Button variant="secondary" onClick={() => setShowCreate(false)}>Cancelar</Button>
              <Button onClick={() => createRule({ ...form, contract_value: parseFloat(form.contract_value)||0 })} disabled={creating || !form.project_id}>
                {creating ? 'Creando...' : 'Crear regla'}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Modal calcular período */}
      {showCompute && (
        <Modal open title={`Calcular reconocimiento — ${showCompute.project_name}`} onClose={() => setShowCompute(null)} width={440}>
          <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
            <div style={{ background:'var(--surface-2)', borderRadius:8, padding:'12px 14px', fontSize:12, color:'var(--text-2)' }}>
              Método: <strong style={{ color:'var(--text-1)' }}>{METHOD_CFG[showCompute.method]?.label}</strong><br/>
              Contrato: <strong style={{ color:'var(--text-1)' }}>{fmtEur(showCompute.contract_value)}</strong>
            </div>
            <div><label style={ls}>Período (mes a calcular)</label>
              <input type="month" value={computePeriod.slice(0,7)} onChange={e=>setComputePeriod(e.target.value+'-01')} style={fs} />
            </div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
              <Button variant="secondary" onClick={() => setShowCompute(null)}>Cancelar</Button>
              <Button onClick={() => compute({ id:showCompute.id, period:computePeriod })} disabled={computing}>
                {computing ? 'Calculando...' : 'Calcular y registrar'}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
