/**
 * RevenuePage — Reconocimiento de ingresos ASC 606 / IFRS 15
 * Configura el método por proyecto y registra entradas mensuales
 */
import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, revenueRecognitionApi, revenueApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { TrendingUp, Lock, LockOpen, RefreshCw } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'
import { useOrgSettings } from '../hooks/useOrgSettings'

const fs = { width:'100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize: "var(--text-xs)", fontWeight:500, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'.07em', display:'block', marginBottom:5 }
const card = { background:'var(--surface-1)', border:'.5px solid var(--surface-4)', borderRadius:12 }

// Methods for existing rules (legacy engine)
const METHOD_CFG = {
  percentage_complete: { label:'% Completado',        desc:'Reconoce proporcionalmente al avance de tareas', icon:'📊' },
  time_and_material:   { label:'T&M',                 desc:'Reconoce al registrar horas facturables', icon:'⏱' },
  straight_line:       { label:'Línea recta',          desc:'Distribuye el contrato en partes iguales por mes', icon:'📈' },
  milestone:           { label:'Por hito',             desc:'Reconoce al alcanzar hitos acordados', icon:'🎯' },
  completed_contract:  { label:'Contrato completado',  desc:'Solo reconoce al cerrar el proyecto', icon:'✅' },
}

// Methods for new ASC 606 engine
const ASC_METHOD_CFG = {
  over_time:    { label:'T&M / Tiempo',    desc:'Proporcional a horas aprobadas en el período', icon:'⏱' },
  milestone:    { label:'Por hito',        desc:'Al completar hitos ligados a obligaciones', icon:'🎯' },
  consumption:  { label:'Bolsa de horas',  desc:'Al consumir horas de la bolsa contratada', icon:'🗂' },
  straight_line:{ label:'Línea recta',     desc:'1/N por mes durante la duración del contrato', icon:'📈' },
}

const MONTHS = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

// ── Obligations panel (per-contract) ─────────────────────────────────────────
function ObligationsPanel({ contractId, onClose, currency }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({ name:'', method:'over_time', standalone_price:'', notes:'' })

  const { data: obs = [], isLoading } = useQuery({
    queryKey: ['asc606-obligations', contractId],
    queryFn: () => revenueRecognitionApi.obligations(contractId).then(r => r.data),
  })

  const reset = () => { setForm({ name:'', method:'over_time', standalone_price:'', notes:'' }); setEditing(null); setShowForm(false) }

  const { mutate: save, isPending: saving } = useMutation({
    mutationFn: d => editing
      ? revenueRecognitionApi.updateObligation(editing.id, d).then(r => r.data)
      : revenueRecognitionApi.createObligation(contractId, d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['asc606-obligations', contractId]); reset() },
    onError: e => toast.error(extractErr(e, 'Error al guardar obligación')),
  })

  const { mutate: del } = useMutation({
    mutationFn: id => revenueRecognitionApi.deleteObligation(id),
    onSuccess: () => qc.invalidateQueries(['asc606-obligations', contractId]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <Modal open onClose={onClose} title="Obligaciones de desempeño" width={560}>
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        {isLoading ? <Spinner /> : obs.length === 0 && !showForm ? (
          <EmptyState icon="📋" title="Sin obligaciones" description="Añade las obligaciones de desempeño de este contrato" />
        ) : (
          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
            {obs.map(ob => {
              const mCfg = ASC_METHOD_CFG[ob.method] || { label: ob.method, icon:'•' }
              return (
                <div key={ob.id} style={{ background:'var(--surface-2)', border:'.5px solid var(--surface-4)', borderRadius:8, padding:'10px 14px', display:'flex', alignItems:'center', gap:12 }}>
                  <div style={{ flex:1, minWidth:0 }}>
                    <div style={{ fontSize: "var(--text-base)", fontWeight:500 }}>{ob.name}</div>
                    <div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginTop:2 }}>
                      {mCfg.icon} {mCfg.label}
                      {ob.standalone_price > 0 && <span style={{ marginLeft:8 }}>{fmtEur(ob.standalone_price, currency)}</span>}
                      {ob.is_satisfied && <span style={{ marginLeft:8, color:'var(--success)' }}>✓ Completada</span>}
                    </div>
                  </div>
                  <div style={{ display:'flex', gap:6, flexShrink:0 }}>
                    <button onClick={() => { setEditing(ob); setForm({ name:ob.name, method:ob.method||'over_time', standalone_price:ob.standalone_price||'', notes:ob.notes||'' }); setShowForm(true) }}
                      style={{ background:'none', border:'1px solid var(--surface-4)', borderRadius:6, padding:'3px 8px', cursor:'pointer', fontSize: "var(--text-xs)", color:'var(--text-2)' }}>✏</button>
                    <button onClick={() => del(ob.id)}
                      style={{ background:'none', border:'1px solid rgba(239,68,68,0.2)', borderRadius:6, padding:'3px 8px', cursor:'pointer', fontSize: "var(--text-xs)", color:'var(--danger)' }}>🗑</button>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {showForm ? (
          <div style={{ border:'.5px solid var(--surface-4)', borderRadius:8, padding:'14px', display:'flex', flexDirection:'column', gap:10 }}>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
              <div><label style={ls}>Nombre</label>
                <input value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} style={fs} placeholder="Ej: Fase 1 — Análisis" />
              </div>
              <div><label style={ls}>Método</label>
                <select value={form.method} onChange={e=>setForm(f=>({...f,method:e.target.value}))} style={fs}>
                  {Object.entries(ASC_METHOD_CFG).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
                </select>
              </div>
            </div>
            <div><label style={ls}>Precio de venta independiente (€)</label>
              <input type="number" value={form.standalone_price} onChange={e=>setForm(f=>({...f,standalone_price:e.target.value}))} style={fs} placeholder="0" />
            </div>
            <div><label style={ls}>Notas</label>
              <textarea value={form.notes} onChange={e=>setForm(f=>({...f,notes:e.target.value}))} rows={2} style={{...fs,resize:'vertical'}} />
            </div>
            <div style={{ display:'flex', gap:8, justifyContent:'flex-end' }}>
              <Button variant="secondary" onClick={reset}>Cancelar</Button>
              <Button onClick={() => save({ ...form, standalone_price: parseFloat(form.standalone_price)||0 })} disabled={saving || !form.name.trim()}>
                {saving ? '...' : editing ? 'Guardar' : 'Añadir'}
              </Button>
            </div>
          </div>
        ) : (
          <Button variant="secondary" onClick={() => setShowForm(true)}>+ Añadir obligación</Button>
        )}
      </div>
    </Modal>
  )
}

function fmtEur(n, currency) {
  if (!n && n !== 0) return '—'
  if (!currency) return new Intl.NumberFormat('es-ES', { minimumFractionDigits:0, maximumFractionDigits:0 }).format(n)
  return new Intl.NumberFormat('es-ES', { style:'currency', currency, minimumFractionDigits:0, maximumFractionDigits:0 }).format(n)
}

export default function RevenuePage() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { currency } = useOrgSettings()
  const fmt = (n) => fmtEur(n, currency)
  const [tab, setTab] = useState('summary')
  const [showCreate, setShowCreate] = useState(false)
  const [showCompute, setShowCompute] = useState(null)
  const [form, setForm] = useState({ project_id:'', method:'percentage_complete', contract_value:'', start_date:'', end_date:'', notes:'' })
  const [computePeriod, setComputePeriod] = useState(new Date().toISOString().slice(0,7) + '-01')

  // ── New ASC 606 state ──────────────────────────────────────────────────────
  const currentYear = new Date().getFullYear()
  const currentMonth = new Date().getMonth() + 1
  const [dashYear, setDashYear] = useState(currentYear)
  const [showCreateContract, setShowCreateContract] = useState(false)
  const [showCloseModal, setShowCloseModal] = useState(false)
  const [obligationsFor, setObligationsFor] = useState(null)
  const [entryFilter, setEntryFilter] = useState({ contract_id: '', year: '', month: '' })
  const [closePeriod, setClosePeriod] = useState({ year: currentYear, month: currentMonth, notes: '' })
  const [contractForm, setContractForm] = useState({ project_id:'', name:'', method:'over_time', contract_value:'', currency, start_date:'', end_date:'', duration_months:'', notes:'' })

  // ── Existing queries ───────────────────────────────────────────────────────
  const { data: rules = [], isLoading } = useQuery({ queryKey:['rev-rules'], queryFn:() => revenueApi.rules().then(r=>r.data) })
  const { data: summary } = useQuery({ queryKey:['rev-summary'], queryFn:() => revenueApi.summary().then(r=>r.data) })
  const { data: projects = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data || []) })

  // ── New ASC 606 queries ────────────────────────────────────────────────────
  const { data: asc606Dashboard } = useQuery({
    queryKey: ['asc606-dashboard', dashYear],
    queryFn: () => revenueRecognitionApi.dashboard(dashYear).then(r => r.data),
    enabled: tab === 'asc606',
  })
  const { data: contracts = [], isLoading: contractsLoading } = useQuery({
    queryKey: ['asc606-contracts'],
    queryFn: () => revenueRecognitionApi.contracts().then(r => r.data),
    enabled: tab === 'asc606',
  })
  const { data: periodCloses = [] } = useQuery({
    queryKey: ['asc606-period-closes'],
    queryFn: () => revenueRecognitionApi.periodCloses().then(r => r.data),
    enabled: tab === 'asc606',
  })

  const { data: entries = [], isLoading: entriesLoading } = useQuery({
    queryKey: ['asc606-entries', entryFilter],
    queryFn: () => {
      const p = {}
      if (entryFilter.contract_id) p.contract_id = entryFilter.contract_id
      if (entryFilter.year)        p.year         = entryFilter.year
      if (entryFilter.month)       p.month        = entryFilter.month
      return revenueRecognitionApi.entries(p).then(r => r.data).catch(() => [])
    },
    enabled: tab === 'entries',
  })
  const { mutate: reverseEntry } = useMutation({
    mutationFn: id => revenueRecognitionApi.reverseEntry(id),
    onSuccess: () => { qc.invalidateQueries(['asc606-entries']); toast.success('Entrada revertida') },
    onError: e => toast.error(extractErr(e, 'Error al revertir')),
  })

  // ── Existing mutations ─────────────────────────────────────────────────────
  const { mutate: createRule, isPending:creating } = useMutation({
    mutationFn: d => revenueApi.createRule(d),
    onSuccess: () => { qc.invalidateQueries(['rev-rules']); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: _autoCompute, isPending: _autoComputing } = useMutation({
    mutationFn: () => revenueApi.autoCompute(computePeriod),
    onSuccess: (res) => {
      qc.invalidateQueries(['revenue-rules'])
      toast.success(`Auto-compute: ${res.data.total_recognised?.toLocaleString('es-ES', {style:'currency',currency})} reconocidos`)
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: compute, isPending:computing } = useMutation({
    mutationFn: ({ id, period }) => revenueApi.compute(id, period),
    onSuccess: () => { qc.invalidateQueries(['rev-rules']); qc.invalidateQueries(['rev-summary']); setShowCompute(null) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  // ── New ASC 606 mutations ──────────────────────────────────────────────────
  const { mutate: createContract, isPending: creatingContract } = useMutation({
    mutationFn: d => revenueRecognitionApi.createContract(d),
    onSuccess: () => {
      qc.invalidateQueries(['asc606-contracts'])
      qc.invalidateQueries(['asc606-dashboard', dashYear])
      setShowCreateContract(false)
      toast.success('Contrato creado')
    },
    onError: e => toast.error(extractErr(e, 'Error al crear contrato')),
  })
  const { mutate: closePeriodMut, isPending: closingPeriod } = useMutation({
    mutationFn: d => revenueRecognitionApi.closePeriod(d),
    onSuccess: () => {
      qc.invalidateQueries(['asc606-period-closes'])
      setShowCloseModal(false)
      toast.success(`Período ${closePeriod.year}-${String(closePeriod.month).padStart(2,'0')} cerrado`)
    },
    onError: e => toast.error(extractErr(e, 'Error al cerrar período')),
  })
  const { mutate: reopenPeriodMut } = useMutation({
    mutationFn: ({ year, month }) => revenueRecognitionApi.reopenPeriod(year, month),
    onSuccess: () => { qc.invalidateQueries(['asc606-period-closes']); toast.success('Período reabierto') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: runMonthly, isPending: runningMonthly } = useMutation({
    mutationFn: d => revenueRecognitionApi.runMonthly(d),
    onSuccess: (res) => {
      qc.invalidateQueries(['asc606-dashboard', dashYear])
      const r = res.data.recognized
      toast.success(`Reconocimiento completado: T&M ${fmt(r?.over_time)}, Línea recta ${fmt(r?.straight_line)}`)
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  // ── Chart data ─────────────────────────────────────────────────────────────
  const byMonth = summary?.by_month || []
  const chartData = byMonth.slice(-12).map(m => ({
    mes: (m.month || '').slice(0, 7),
    Reconocido: Math.round(Number(m.recognised) || 0),
    Diferido:   Math.round(Number(m.deferred) || 0),
  }))

  const asc606ChartData = (asc606Dashboard?.by_month || []).map(m => ({
    mes: MONTHS[m.month - 1],
    Reconocido: Math.round(Number(m.recognized) || 0),
    Diferido:   Math.round(Number(m.deferred) || 0),
    Unbilled:   Math.round(Number(m.unbilled) || 0),
  }))

  const TABS = [
    { id:'summary', label:'Resumen' },
    { id:'rules',   label:'Reglas por proyecto' },
    { id:'asc606',  label:'Contratos ASC 606' },
    { id:'entries', label:'Entradas contables' },
    { id:'info',    label:'ASC 606 / IFRS 15' },
  ]

  const closedPeriodKeys = new Set(periodCloses.map(pc => `${pc.period_year}-${pc.period_month}`))

  return (
    <PageShell>
      <PageHeader icon={<TrendingUp size={18} />} title={t('profitability.revenue')} subtitle={t('profitability.revenue_subtitle')} />

      {/* KPIs */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:14, marginBottom:28 }}>
        {[
          { label:'Total reconocido', value:fmt(summary?.total_recognised), icon:'✅' },
          { label:'Total diferido',   value:fmt(summary?.total_deferred),   icon:'⏳' },
          { label:'Proyectos activos', value:rules.length,                      icon:'⬡' },
          { label:'Entradas registradas', value:summary?.entry_count || 0,      icon:'📋' },
        ].map((k,i) => (
          <div key={i} style={{ background:'var(--surface-2)', borderRadius:10, padding:'16px 18px' }}>
            <div style={{ fontSize: "var(--text-xl)", marginBottom:6 }}>{k.icon}</div>
            <div style={{ fontSize: "var(--text-xl-em)", fontWeight:500, marginBottom:2 }}>{k.value}</div>
            <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)' }}>{k.label}</div>
          </div>
        ))}
      </div>

      {/* Tab nav */}
      <div style={{ display:'flex', gap:8, marginBottom:24 }}>
        {TABS.map(tb => (
          <button key={tb.id} onClick={() => setTab(tb.id)}
            style={{ padding:'8px 16px', borderRadius:8, border:`.5px solid ${tab===tb.id?'rgba(0,212,255,0.25)':'var(--surface-4)'}`, background:tab===tb.id?'var(--accent-muted)':'transparent', color:tab===tb.id?'var(--accent)':'var(--text-2)', fontSize: "var(--text-base)", fontWeight:500, cursor:'pointer', fontFamily:'inherit' }}>
            {tb.label}
          </button>
        ))}
      </div>

      {/* ── Resumen ── */}
      {tab === 'summary' && (
        <div>
          {chartData.length > 0 ? (
            <div style={{ ...card, padding:'20px 24px' }}>
              <div style={{ fontSize: "var(--text-base)", fontWeight:500, marginBottom:16 }}>Ingresos reconocidos vs diferidos por mes</div>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={chartData}>
                  <XAxis dataKey="mes" tick={{ fontSize: "var(--text-xs)" }} />
                  <YAxis tickFormatter={v => `${Math.round(v/1000)}k€`} tick={{ fontSize: "var(--text-xs)" }} />
                  <Tooltip formatter={(v,n) => [fmt(v), n]} />
                  <Legend />
                  <Bar dataKey="Reconocido" fill="var(--success)" radius={[3,3,0,0]} />
                  <Bar dataKey="Diferido"   fill="var(--warning)" radius={[3,3,0,0]} />
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
                          <span style={{ fontSize: "var(--text-md)", fontWeight:500 }}>{r.project_name}</span>
                          <span style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', padding:'1px 6px', borderRadius:4, background:'var(--surface-2)' }}>{r.project_code}</span>
                          <span style={{ fontSize: "var(--text-xs)", padding:'1px 6px', borderRadius:4, background:'var(--accent-muted)', color:'var(--accent)' }}>{mCfg.icon} {mCfg.label}</span>
                        </div>
                        <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:16, marginBottom:10 }}>
                          <div><div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginBottom:2 }}>Valor contrato</div><div style={{ fontSize: "var(--text-md)", fontWeight:500 }}>{fmt(r.contract_value)}</div></div>
                          <div><div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginBottom:2 }}>Reconocido</div><div style={{ fontSize: "var(--text-md)", fontWeight:500, color:'var(--success)' }}>{fmt(r.total_recognised)}</div></div>
                          <div><div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginBottom:2 }}>Diferido</div><div style={{ fontSize: "var(--text-md)", fontWeight:500, color:'var(--warning)' }}>{fmt(r.total_deferred)}</div></div>
                          <div><div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginBottom:2 }}>Entradas</div><div style={{ fontSize: "var(--text-md)", fontWeight:500 }}>{r.entry_count}</div></div>
                        </div>
                        {r.contract_value > 0 && (
                          <div>
                            <div style={{ height:6, background:'var(--surface-2)', borderRadius:3, overflow:'hidden' }}>
                              <div style={{ height:'100%', background:'var(--success-bg)', width:`${Math.min(pct,100)}%`, borderRadius:3 }} />
                            </div>
                            <div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginTop:3 }}>{pct}% reconocido</div>
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

      {/* ── ASC 606 Contratos (nuevo motor) ── */}
      {tab === 'asc606' && (
        <div style={{ display:'flex', flexDirection:'column', gap:20 }}>
          {/* Top bar */}
          <div style={{ display:'flex', gap:10, alignItems:'center', justifyContent:'space-between' }}>
            <div style={{ display:'flex', gap:10, alignItems:'center' }}>
              <select value={dashYear} onChange={e => setDashYear(Number(e.target.value))} style={{ ...fs, width:'auto' }}>
                {[currentYear-1, currentYear, currentYear+1].map(y => <option key={y} value={y}>{y}</option>)}
              </select>
              <Button variant="secondary" onClick={() => runMonthly({ year: dashYear, month: currentMonth })} disabled={runningMonthly}>
                <RefreshCw size={13} style={{ marginRight:4 }} />{runningMonthly ? 'Procesando...' : 'Ejecutar reconocimiento'}
              </Button>
            </div>
            <div style={{ display:'flex', gap:10 }}>
              <Button variant="secondary" onClick={() => setShowCloseModal(true)}><Lock size={13} style={{ marginRight:4 }} />Cerrar período</Button>
              <Button onClick={() => setShowCreateContract(true)}>+ Nuevo contrato</Button>
            </div>
          </div>

          {/* Dashboard KPIs */}
          {asc606Dashboard && (
            <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:12 }}>
              {[
                { label:'Total reconocido', value: fmt(asc606Dashboard.total_recognized), icon:'✅' },
                { label:'Contratos activos', value: asc606Dashboard.contracts?.length || 0, icon:'📑' },
                { label:'Entradas contables', value: asc606Dashboard.entry_count || 0, icon:'📋' },
              ].map((k,i) => (
                <div key={i} style={{ background:'var(--surface-2)', borderRadius:10, padding:'14px 16px' }}>
                  <div style={{ fontSize: "var(--text-lg-em)", marginBottom:4 }}>{k.icon}</div>
                  <div style={{ fontSize: "var(--text-xl)", fontWeight:500, marginBottom:2 }}>{k.value}</div>
                  <div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)' }}>{k.label}</div>
                </div>
              ))}
            </div>
          )}

          {/* Chart */}
          {asc606ChartData.length > 0 && (
            <div style={{ ...card, padding:'20px 24px' }}>
              <div style={{ fontSize: "var(--text-base)", fontWeight:500, marginBottom:16 }}>Reconocimiento ASC 606 — {dashYear}</div>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={asc606ChartData}>
                  <XAxis dataKey="mes" tick={{ fontSize: "var(--text-xs)" }} />
                  <YAxis tickFormatter={v => `${Math.round(v/1000)}k€`} tick={{ fontSize: "var(--text-xs)" }} />
                  <Tooltip formatter={(v,n) => [fmt(v), n]} />
                  <Legend />
                  <Bar dataKey="Reconocido" fill="var(--success)" radius={[3,3,0,0]} />
                  <Bar dataKey="Diferido"   fill="var(--warning)" radius={[3,3,0,0]} />
                  <Bar dataKey="Unbilled"   fill="var(--accent)" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Period closes */}
          {periodCloses.length > 0 && (
            <div style={{ ...card, padding:'16px 20px' }}>
              <div style={{ fontSize: "var(--text-sm)", fontWeight:500, marginBottom:10, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'.06em' }}>Cierres contables</div>
              <div style={{ display:'flex', flexWrap:'wrap', gap:8 }}>
                {periodCloses.map(pc => (
                  <div key={pc.id} style={{ display:'flex', alignItems:'center', gap:6, padding:'4px 10px', borderRadius:6, background:'var(--surface-2)', fontSize: "var(--text-sm)" }}>
                    <Lock size={11} style={{ color:'var(--accent)' }} />
                    <span>{pc.period_year}-{String(pc.period_month).padStart(2,'0')}</span>
                    <button
                      onClick={() => reopenPeriodMut({ year: pc.period_year, month: pc.period_month })}
                      style={{ background:'none', border:'none', cursor:'pointer', color:'var(--text-3)', padding:0, lineHeight:1 }}
                      title="Reabrir período"
                    >
                      <LockOpen size={11} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Contracts list */}
          <div>
            <div style={{ fontSize: "var(--text-sm)", fontWeight:500, marginBottom:10, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'.06em' }}>Contratos de reconocimiento</div>
            {contractsLoading ? <Spinner /> : contracts.length === 0 ? (
              <EmptyState icon="📑" title="Sin contratos ASC 606" description="Crea un contrato para configurar el reconocimiento de ingresos por proyecto" />
            ) : (
              <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
                {contracts.map(c => {
                  const mCfg = ASC_METHOD_CFG[c.method] || { label: c.method, icon:'•' }
                  return (
                    <div key={c.id} style={{ ...card, padding:'14px 18px' }}>
                      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
                        <div>
                          <div style={{ display:'flex', gap:8, alignItems:'center', marginBottom:6 }}>
                            <span style={{ fontSize: "var(--text-md)", fontWeight:500 }}>{c.name}</span>
                            <span style={{ fontSize: "var(--text-xs)", padding:'1px 6px', borderRadius:4, background:'var(--accent-muted)', color:'var(--accent)' }}>
                              {mCfg.icon} {mCfg.label}
                            </span>
                            {!c.is_active && (
                              <span style={{ fontSize: "var(--text-xs)", padding:'1px 6px', borderRadius:4, background:'var(--surface-3)', color:'var(--text-3)' }}>Inactivo</span>
                            )}
                          </div>
                          <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:16, marginBottom:10 }}>
                            <div><div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginBottom:1 }}>Valor contrato</div><div style={{ fontSize: "var(--text-base)", fontWeight:500 }}>{fmt(c.contract_value)}</div></div>
                            <div><div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginBottom:1 }}>Moneda</div><div style={{ fontSize: "var(--text-base)" }}>{c.currency}</div></div>
                            <div><div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginBottom:1 }}>Inicio</div><div style={{ fontSize: "var(--text-base)" }}>{c.start_date || '—'}</div></div>
                            <div><div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginBottom:1 }}>Fin</div><div style={{ fontSize: "var(--text-base)" }}>{c.end_date || c.duration_months ? `${c.duration_months}m` : '—'}</div></div>
                          </div>
                          <button onClick={() => setObligationsFor(c.id)}
                            style={{ fontSize: "var(--text-xs)", padding:'3px 10px', borderRadius:6, border:'.5px solid var(--surface-4)', background:'transparent', color:'var(--text-2)', cursor:'pointer', fontFamily:'inherit' }}>
                            📋 Obligaciones de desempeño
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Entradas contables ── */}
      {tab === 'entries' && (
        <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
          {/* Filters */}
          <div style={{ display:'grid', gridTemplateColumns:'1fr auto auto auto', gap:10, alignItems:'flex-end' }}>
            <div>
              <label style={ls}>Contrato</label>
              <select value={entryFilter.contract_id} onChange={e => setEntryFilter(f=>({...f, contract_id:e.target.value}))} style={fs}>
                <option value="">Todos los contratos</option>
                {contracts.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label style={ls}>Año</label>
              <select value={entryFilter.year} onChange={e => setEntryFilter(f=>({...f, year:e.target.value}))} style={{...fs, width:100}}>
                <option value="">Todos</option>
                {[currentYear-1, currentYear, currentYear+1].map(y => <option key={y} value={y}>{y}</option>)}
              </select>
            </div>
            <div>
              <label style={ls}>Mes</label>
              <select value={entryFilter.month} onChange={e => setEntryFilter(f=>({...f, month:e.target.value}))} style={{...fs, width:110}}>
                <option value="">Todos</option>
                {MONTHS.map((m,i) => <option key={i+1} value={i+1}>{i+1} — {m}</option>)}
              </select>
            </div>
            {(entryFilter.contract_id||entryFilter.year||entryFilter.month) && (
              <button onClick={() => setEntryFilter({ contract_id:'', year:'', month:'' })}
                style={{ alignSelf:'flex-end', padding:'9px 14px', borderRadius:8, border:'.5px solid var(--surface-4)', background:'transparent', color:'var(--text-2)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit' }}>
                ✕ Limpiar
              </button>
            )}
          </div>

          {/* Table */}
          {entriesLoading ? <Spinner /> : entries.length === 0 ? (
            <EmptyState icon="📋" title="Sin entradas contables" description="Las entradas se generan al ejecutar el reconocimiento mensual" />
          ) : (
            <div style={{ ...card, overflowX:'auto' }}>
              <table style={{ width:'100%', borderCollapse:'collapse', fontSize: "var(--text-base)" }}>
                <thead>
                  <tr style={{ borderBottom:'1px solid var(--surface-4)', background:'var(--surface-3)' }}>
                    {['Contrato','Período','Método','Reconocido','Diferido','Estado',''].map((h,i) => (
                      <th key={h||i} style={{ padding:'10px 14px', textAlign:i<=1?'left':'center', fontSize: "var(--text-2xs)", fontWeight:700, color:'var(--text-3)', textTransform:'uppercase', letterSpacing:'.07em', whiteSpace:'nowrap' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e, idx) => {
                    const mCfg = ASC_METHOD_CFG[e.method] || { label:e.method||'—', icon:'•' }
                    const isReversed = e.is_reversed || e.status === 'reversed'
                    return (
                      <tr key={e.id} style={{ borderBottom:'1px solid var(--surface-4)', background: idx%2===0?'transparent':'rgba(255,255,255,0.02)', opacity: isReversed ? 0.5 : 1 }}>
                        <td style={{ padding:'10px 14px' }}>
                          <div style={{ fontWeight:500 }}>{e.contract_name || e.contract_id}</div>
                          {e.obligation_name && <div style={{ fontSize: "var(--text-xs)", color:'var(--text-3)' }}>{e.obligation_name}</div>}
                        </td>
                        <td style={{ padding:'10px 14px', fontFamily:'var(--font-mono)', fontSize: "var(--text-sm)" }}>
                          {e.period_year}-{String(e.period_month).padStart(2,'0')}
                        </td>
                        <td style={{ padding:'10px 14px', textAlign:'center' }}>
                          <span style={{ fontSize: "var(--text-xs)" }}>{mCfg.icon} {mCfg.label}</span>
                        </td>
                        <td style={{ padding:'10px 14px', textAlign:'center', fontWeight:600, color:'var(--success)' }}>
                          {fmt(e.recognized_amount ?? e.amount)}
                        </td>
                        <td style={{ padding:'10px 14px', textAlign:'center', color:'var(--warning)' }}>
                          {fmt(e.deferred_amount ?? 0)}
                        </td>
                        <td style={{ padding:'10px 14px', textAlign:'center' }}>
                          {isReversed
                            ? <span style={{ fontSize: "var(--text-xs)", color:'var(--danger)' }}>Revertida</span>
                            : <span style={{ fontSize: "var(--text-xs)", color:'var(--success)' }}>Activa</span>}
                        </td>
                        <td style={{ padding:'10px 14px', textAlign:'center' }}>
                          {!isReversed && (
                            <button onClick={() => { if (window.confirm('¿Revertir esta entrada?')) reverseEntry(e.id) }}
                              style={{ fontSize: "var(--text-xs)", padding:'3px 9px', borderRadius:6, border:'1px solid rgba(239,68,68,0.3)', background:'transparent', color:'var(--danger)', cursor:'pointer', fontFamily:'inherit' }}>
                              ↩ Revertir
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Info ASC 606 ── */}
      {tab === 'info' && (
        <div style={{ ...card, padding:'24px 28px', maxWidth:700 }}>
          <div style={{ fontSize: "var(--text-md)", fontWeight:500, marginBottom:16 }}>ASC 606 / IFRS 15 — Los 5 pasos</div>
          {[
            ['1. Identificar el contrato', 'Acuerdo con el cliente con términos comerciales claros y probabilidad de cobro.'],
            ['2. Identificar las obligaciones', 'Cada entregable distinto (módulo, fase, servicio) es una obligación de desempeño separada.'],
            ['3. Determinar el precio', 'Precio total del contrato, incluyendo variables, descuentos y opciones.'],
            ['4. Asignar el precio', 'Distribuir el precio entre cada obligación según valor relativo de mercado.'],
            ['5. Reconocer los ingresos', 'Reconocer al satisfacer cada obligación: a lo largo del tiempo o en un momento puntual.'],
          ].map(([title, desc], i) => (
            <div key={i} style={{ display:'flex', gap:14, padding:'12px 0', borderBottom:'.5px solid var(--surface-4)' }}>
              <div style={{ width:28, height:28, borderRadius:'50%', background:'var(--accent-muted)', color:'var(--accent)', display:'flex', alignItems:'center', justifyContent:'center', fontSize: "var(--text-sm)", fontWeight:700, flexShrink:0 }}>{i+1}</div>
              <div>
                <div style={{ fontSize: "var(--text-base)", fontWeight:500, marginBottom:3 }}>{title}</div>
                <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)' }}>{desc}</div>
              </div>
            </div>
          ))}
          <div style={{ marginTop:16, display:'flex', flexDirection:'column', gap:10 }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight:500 }}>Métodos disponibles</div>
            {Object.entries(ASC_METHOD_CFG).map(([k, v]) => (
              <div key={k} style={{ display:'flex', gap:10, padding:'8px 12px', background:'var(--surface-2)', borderRadius:8 }}>
                <span style={{ fontSize: "var(--text-lg)" }}>{v.icon}</span>
                <div>
                  <div style={{ fontSize: "var(--text-sm)", fontWeight:500 }}>{v.label}</div>
                  <div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)' }}>{v.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Modal nueva regla (legacy) ── */}
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

      {/* ── Modal calcular período (legacy) ── */}
      {showCompute && (
        <Modal open title={`Calcular reconocimiento — ${showCompute.project_name}`} onClose={() => setShowCompute(null)} width={440}>
          <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
            <div style={{ background:'var(--surface-2)', borderRadius:8, padding:'12px 14px', fontSize: "var(--text-sm)", color:'var(--text-2)' }}>
              Método: <strong style={{ color:'var(--text-1)' }}>{METHOD_CFG[showCompute.method]?.label}</strong><br/>
              Contrato: <strong style={{ color:'var(--text-1)' }}>{fmt(showCompute.contract_value)}</strong>
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

      {/* ── Modal nuevo contrato ASC 606 ── */}
      {showCreateContract && (
        <Modal open title="Nuevo contrato ASC 606" onClose={() => setShowCreateContract(false)} width={540}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div><label style={ls}>Proyecto</label>
              <select value={contractForm.project_id} onChange={e=>setContractForm(f=>({...f,project_id:e.target.value}))} style={fs}>
                <option value="">Seleccionar proyecto...</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
              </select>
            </div>
            <div><label style={ls}>Nombre del contrato</label>
              <input value={contractForm.name} onChange={e=>setContractForm(f=>({...f,name:e.target.value}))} style={fs} placeholder="Ej: Contrato desarrollo Q1 2026" />
            </div>
            <div><label style={ls}>Método de reconocimiento</label>
              <select value={contractForm.method} onChange={e=>setContractForm(f=>({...f,method:e.target.value}))} style={fs}>
                {Object.entries(ASC_METHOD_CFG).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label} — {v.desc}</option>)}
              </select>
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
              <div><label style={ls}>Valor del contrato</label>
                <input type="number" value={contractForm.contract_value} onChange={e=>setContractForm(f=>({...f,contract_value:e.target.value}))} style={fs} placeholder="50000" />
              </div>
              <div><label style={ls}>Moneda</label>
                <select value={contractForm.currency} onChange={e=>setContractForm(f=>({...f,currency:e.target.value}))} style={fs}>
                  {['EUR','USD','GBP','CHF'].map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
              <div><label style={ls}>Fecha inicio</label><input type="date" value={contractForm.start_date} onChange={e=>setContractForm(f=>({...f,start_date:e.target.value}))} style={fs} /></div>
              <div><label style={ls}>Fecha fin</label><input type="date" value={contractForm.end_date} onChange={e=>setContractForm(f=>({...f,end_date:e.target.value}))} style={fs} /></div>
            </div>
            {contractForm.method === 'straight_line' && (
              <div><label style={ls}>Duración (meses) — alternativa a fecha fin</label>
                <input type="number" value={contractForm.duration_months} onChange={e=>setContractForm(f=>({...f,duration_months:e.target.value}))} style={fs} placeholder="12" />
              </div>
            )}
            <div><label style={ls}>Notas</label>
              <textarea value={contractForm.notes} onChange={e=>setContractForm(f=>({...f,notes:e.target.value}))} rows={2} style={{...fs,resize:'vertical'}} />
            </div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
              <Button variant="secondary" onClick={() => setShowCreateContract(false)}>Cancelar</Button>
              <Button
                onClick={() => createContract({
                  ...contractForm,
                  contract_value: parseFloat(contractForm.contract_value) || 0,
                  duration_months: contractForm.duration_months ? parseInt(contractForm.duration_months) : null,
                })}
                disabled={creatingContract || !contractForm.project_id || !contractForm.name}
              >
                {creatingContract ? 'Creando...' : 'Crear contrato'}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Modal cerrar período ── */}
      {showCloseModal && (
        <Modal open title="Cerrar período contable" onClose={() => setShowCloseModal(false)} width={420}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div style={{ background:'var(--warning-bg)', borderRadius:8, padding:'10px 12px', fontSize: "var(--text-sm)", color:'var(--warning)' }}>
              Una vez cerrado, no se podrán crear ni revertir entradas para este período.
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
              <div><label style={ls}>Año</label>
                <input type="number" value={closePeriod.year} onChange={e=>setClosePeriod(p=>({...p,year:parseInt(e.target.value)}))} style={fs} />
              </div>
              <div><label style={ls}>Mes</label>
                <select value={closePeriod.month} onChange={e=>setClosePeriod(p=>({...p,month:parseInt(e.target.value)}))} style={fs}>
                  {MONTHS.map((m,i) => <option key={i+1} value={i+1}>{i+1} — {m}</option>)}
                </select>
              </div>
            </div>
            {closedPeriodKeys.has(`${closePeriod.year}-${closePeriod.month}`) && (
              <div style={{ fontSize: "var(--text-sm)", color:'var(--danger)', padding:'6px 10px', background:'var(--danger-bg)', borderRadius:6 }}>
                Este período ya está cerrado.
              </div>
            )}
            <div><label style={ls}>Notas (opcional)</label>
              <textarea value={closePeriod.notes} onChange={e=>setClosePeriod(p=>({...p,notes:e.target.value}))} rows={2} style={{...fs,resize:'vertical'}} />
            </div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
              <Button variant="secondary" onClick={() => setShowCloseModal(false)}>Cancelar</Button>
              <Button
                onClick={() => closePeriodMut({ year: closePeriod.year, month: closePeriod.month, notes: closePeriod.notes || null })}
                disabled={closingPeriod || closedPeriodKeys.has(`${closePeriod.year}-${closePeriod.month}`)}
              >
                {closingPeriod ? 'Cerrando...' : 'Cerrar período'}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Modal obligaciones ── */}
      {obligationsFor && <ObligationsPanel contractId={obligationsFor} currency={currency} onClose={() => setObligationsFor(null)} />}
    </PageShell>
  )
}
