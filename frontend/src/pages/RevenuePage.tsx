/**
 * RevenuePage — Reconocimiento de ingresos ASC 606 / IFRS 15
 * Configura el método por proyecto y registra entradas mensuales
 */
import { useState, type CSSProperties, useId } from 'react'
import { extractErr, localeActivo } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, revenueRecognitionApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { TrendingUp, Lock, LockOpen, RefreshCw } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'
import { useOrgSettings } from '../hooks/useOrgSettings'
import { openConfirmGlobal } from '../context/ConfirmContext'
import DateInput from '../components/ui/DateInput'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
const fs: CSSProperties = { width:'100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:500, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'.07em', display:'block', marginBottom:5 }
const card: CSSProperties = { background:'var(--surface-1)', border:'.5px solid var(--surface-4)', borderRadius:12 }

type MethodCfg = { label: string; desc?: string; icon: string }

// Methods for new ASC 606 engine
const ASC_METHOD_CFG: Record<string, MethodCfg> = {
  over_time:    { label:'T&M / Tiempo',    desc:'Proporcional a horas aprobadas en el período', icon:'⏱' },
  milestone:    { label:'Por hito',        desc:'Al completar hitos ligados a obligaciones', icon:'🎯' },
  consumption:  { label:'Bolsa de horas',  desc:'Al consumir horas de la bolsa contratada', icon:'🗂' },
  straight_line:{ label:'Línea recta',     desc:'1/N por mes durante la duración del contrato', icon:'📈' },
  percentage_complete: { label:'% Completado', desc:'Contrato × tareas hechas / tareas (sin canceladas)', icon:'📊' },
  completed_contract:  { label:'Contrato completado', desc:'Todo el importe el mes en que el proyecto cierra', icon:'✅' },
}

/** `_serialize_obligation` (app/services/revenue_service.py). */
interface Obligation {
  id: string
  contract_id: string
  milestone_id: string | null
  name: string
  allocated_pct: number
  allocated_amount: number
  is_satisfied: boolean
  satisfied_date: string | null
  // Revisión 158 (auditoría 2026-11): antes el modelo no los tenía y el alta daba 500.
  method: string | null
  standalone_price: number | null
  notes: string | null
}

type ObligationPayload = { name: string; method: string; standalone_price: number; notes: string }

/** `_serialize_contract` (app/services/revenue_service.py). */
interface RevenueContract {
  id: string
  project_id: string | null
  client_id: string | null
  name: string
  contract_value: number
  currency: string
  method: string | null
  start_date: string | null
  end_date: string | null
  duration_months: number | null
  is_active: boolean
  notes: string | null
  created_at: string | null
}

/** `_serialize_entry` (app/services/revenue_service.py). */
interface RevenueEntry {
  id: string
  rev_contract_id: string
  entry_type: string | null
  amount: number
  currency: string
  period_year: number
  period_month: number
  milestone_id: string | null
  description: string | null
  reverses_entry_id: string | null
  created_by: string | null
  created_at: string | null
  // Los añade `serialize_entries` (auditoría 2026-11): antes la tabla los leía y no llegaban.
  contract_name: string | null
  method: string | null
  is_reversed: boolean
}

/** `_serialize_period_close` (app/services/revenue_service.py). */
interface PeriodClose {
  id: string
  period_year: number
  period_month: number
  closed_by: string | null
  closed_at: string | null
  notes: string | null
}

/** `get_asc606_dashboard` (app/services/revenue_service.py). */
interface Asc606MonthRow { month: number; year: number; recognized: number; deferred: number; unbilled: number }
interface Asc606Dashboard {
  year: number
  total_recognized: number
  entry_count: number
  by_month: Asc606MonthRow[]
  contracts: RevenueContract[]
}

type ContractPayload = {
  project_id: string; name: string; method: string; contract_value: number; currency: string
  start_date: string; end_date: string; duration_months: number | null; notes: string
}
type ClosePeriodPayload = { year: number; month: number; notes: string | null }
type RunMonthlyPayload = { year: number; month: number }
type EntryParams = { contract_id?: string; year?: string; month?: string }

const MONTHS = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

// ── Obligations panel (per-contract) ─────────────────────────────────────────
function ObligationsPanel({ contractId, onClose, currency }: { contractId: string; onClose: () => void; currency?: string }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<Obligation | null>(null)
  const [form, setForm] = useState({ name:'', method:'over_time', standalone_price:'', notes:'' })

  const { data: obs = [], isLoading } = useQuery<Obligation[]>({
    queryKey: ['asc606-obligations', contractId],
    queryFn: () => revenueRecognitionApi.obligations(contractId).then(r => r.data),
  })

  const reset = () => { setForm({ name:'', method:'over_time', standalone_price:'', notes:'' }); setEditing(null); setShowForm(false) }

  const { mutate: save, isPending: saving } = useMutation({
    mutationFn: (d: ObligationPayload) => editing
      ? revenueRecognitionApi.updateObligation(editing.id, d).then(r => r.data)
      : revenueRecognitionApi.createObligation(contractId, d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['asc606-obligations', contractId] }); reset() },
    onError: e => toast.error(extractErr(e, 'Error al guardar obligación')),
  })

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => revenueRecognitionApi.deleteObligation(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['asc606-obligations', contractId] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <Modal open onClose={onClose} title={t('revenue.obligaciones_de_desempeno')} width={560}>
      <div className="u-stack-12">
        {isLoading ? <Spinner /> : obs.length === 0 && !showForm ? (
          <EmptyState icon="📋" title={t('revenue.sin_obligaciones')} description="Añade las obligaciones de desempeño de este contrato" />
        ) : (
          <div className="u-stack-8">
            {obs.map(ob => {
              const mCfg = ASC_METHOD_CFG[ob.method ?? ''] || { label: ob.method || '—', icon:'•' }
              return (
                <div key={ob.id} style={{ background:'var(--surface-2)', border:'.5px solid var(--surface-4)', borderRadius:8, padding:'10px 14px', display:'flex', alignItems:'center', gap:12 }}>
                  <div className="u-flex1-min0">
                    <div style={{ fontSize: "var(--text-base)", fontWeight:500 }}>{ob.name}</div>
                    <div className="u-text2-xs-mt2">
                      {mCfg.icon} {mCfg.label}
                      {(ob.standalone_price ?? 0) > 0 && <span style={{ marginLeft:8 }}>{fmtEur(ob.standalone_price ?? 0, currency)}</span>}
                      {ob.is_satisfied && <span style={{ marginLeft:8, color:'var(--success)' }}>✓ Completada</span>}
                    </div>
                  </div>
                  <div style={{ display:'flex', gap:6, flexShrink:0 }}>
                    <button onClick={() => { setEditing(ob); setForm({ name:ob.name, method:ob.method||'over_time', standalone_price:String(ob.standalone_price||''), notes:ob.notes||'' }); setShowForm(true) }}
                      style={{ background:'none', border:'1px solid var(--surface-4)', borderRadius:'var(--radius-sm)', padding:'3px 8px', cursor:'pointer', fontSize: "var(--text-xs)", color:'var(--text-2)' }}>✏</button>
                    <button onClick={() => del(ob.id)}
                      style={{ background:'none', border:'1px solid rgba(239,68,68,0.2)', borderRadius:'var(--radius-sm)', padding:'3px 8px', cursor:'pointer', fontSize: "var(--text-xs)", color:'var(--danger)' }}>🗑</button>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {showForm ? (
          <div style={{ border:'.5px solid var(--surface-4)', borderRadius:8, padding:'14px', display:'flex', flexDirection:'column', gap:10 }}>
            <div className="u-grid2-10">
              <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Nombre</label>
                <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} style={fs} placeholder={t('revenue.ej_fase_1_analisis')} />
              </div>
              <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('revenue.metodo')}</label>
                <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.method} onChange={e=>setForm(f=>({...f,method:e.target.value}))} style={fs}>
                  {Object.entries(ASC_METHOD_CFG).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
                </select>
              </div>
            </div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>{t('revenue.precio_de_venta_independiente')}</label>
              <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" value={form.standalone_price} onChange={e=>setForm(f=>({...f,standalone_price:e.target.value}))} style={fs} placeholder="0" />
            </div>
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>Notas</label>
              <textarea id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.notes} onChange={e=>setForm(f=>({...f,notes:e.target.value}))} rows={2} style={{...fs,resize:'vertical'}} />
            </div>
            <div className="u-actions-8">
              <Button variant="secondary" onClick={reset}>Cancelar</Button>
              <Button onClick={() => save({ ...form, standalone_price: parseFloat(form.standalone_price)||0 })} disabled={saving || !form.name.trim()}>
                {saving ? '...' : editing ? 'Guardar' : 'Añadir'}
              </Button>
            </div>
          </div>
        ) : (
          <Button variant="secondary" onClick={() => setShowForm(true)}>{t('revenue.anadir_obligacion')}</Button>
        )}
      </div>
    </Modal>
  )
}

function fmtEur(n: number | null | undefined, currency?: string) {
  if (!n && n !== 0) return '—'
  if (!currency) return new Intl.NumberFormat(localeActivo(), { minimumFractionDigits:0, maximumFractionDigits:0 }).format(n)
  return new Intl.NumberFormat(localeActivo(), { style:'currency', currency, minimumFractionDigits:0, maximumFractionDigits:0 }).format(n)
}

export default function RevenuePage() {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { currency, currencies: monedasDeLaEmpresa } = useOrgSettings()
  const fmt = (n: number | null | undefined) => fmtEur(n, currency)
  const [tab, setTab] = useState('asc606')
  // El último mes terminado: reconocer o cerrar el mes en curso lo hace con datos a medias.
  const hoy = new Date()
  const cerradoY = hoy.getMonth() === 0 ? hoy.getFullYear() - 1 : hoy.getFullYear()
  const cerradoM = hoy.getMonth() === 0 ? 12 : hoy.getMonth()

  // ── New ASC 606 state ──────────────────────────────────────────────────────
  const currentYear = new Date().getFullYear()
  const [dashYear, setDashYear] = useState(currentYear)
  // El mes que «Ejecutar reconocimiento» procesa en el ejercicio elegido: el último terminado.
  const mesAEjecutar = dashYear < cerradoY ? 12 : dashYear === cerradoY ? cerradoM : null
  const [showCreateContract, setShowCreateContract] = useState(false)
  const [showCloseModal, setShowCloseModal] = useState(false)
  const [obligationsFor, setObligationsFor] = useState<string | null>(null)
  const [entryFilter, setEntryFilter] = useState({ contract_id: '', year: '', month: '' })
  const [closePeriod, setClosePeriod] = useState({ year: cerradoY, month: cerradoM, notes: '' })
  const [contractForm, setContractForm] = useState({ project_id:'', name:'', method:'over_time', contract_value:'', currency, start_date:'', end_date:'', duration_months:'', notes:'' })

  // `projectsApi.list` recorre todas las páginas y devuelve siempre el array.
  const { data: projects = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data ?? []) })

  // ── New ASC 606 queries ────────────────────────────────────────────────────
  const { data: asc606Dashboard } = useQuery<Asc606Dashboard>({
    queryKey: ['asc606-dashboard', dashYear],
    queryFn: () => revenueRecognitionApi.dashboard(dashYear, undefined).then(r => r.data),
  })
  const { data: contracts = [], isLoading: contractsLoading } = useQuery<RevenueContract[]>({
    queryKey: ['asc606-contracts'],
    queryFn: () => revenueRecognitionApi.contracts(undefined).then(r => r.data),
    enabled: tab === 'asc606',
  })
  const { data: periodCloses = [] } = useQuery<PeriodClose[]>({
    queryKey: ['asc606-period-closes'],
    queryFn: () => revenueRecognitionApi.periodCloses().then(r => r.data),
    enabled: tab === 'asc606',
  })

  const { data: entries = [], isLoading: entriesLoading } = useQuery<RevenueEntry[]>({
    queryKey: ['asc606-entries', entryFilter],
    queryFn: () => {
      const p: EntryParams = {}
      if (entryFilter.contract_id) p.contract_id = entryFilter.contract_id
      if (entryFilter.year)        p.year         = entryFilter.year
      if (entryFilter.month)       p.month        = entryFilter.month
      return revenueRecognitionApi.entries(p).then(r => r.data).catch(() => [])
    },
    enabled: tab === 'entries',
  })
  const { mutate: reverseEntry } = useMutation({
    mutationFn: (id: string) => revenueRecognitionApi.reverseEntry(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['asc606-entries'] }); toast.success('Entrada revertida') },
    onError: e => toast.error(extractErr(e, 'Error al revertir')),
  })

  // ── New ASC 606 mutations ──────────────────────────────────────────────────
  const { mutate: createContract, isPending: creatingContract } = useMutation({
    mutationFn: (d: ContractPayload) => revenueRecognitionApi.createContract(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['asc606-contracts'] })
      qc.invalidateQueries({ queryKey: ['asc606-dashboard', dashYear] })
      setShowCreateContract(false)
      toast.success('Contrato creado')
    },
    onError: e => toast.error(extractErr(e, 'Error al crear contrato')),
  })
  const { mutate: closePeriodMut, isPending: closingPeriod } = useMutation({
    mutationFn: (d: ClosePeriodPayload) => revenueRecognitionApi.closePeriod(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['asc606-period-closes'] })
      setShowCloseModal(false)
      toast.success(`Período ${closePeriod.year}-${String(closePeriod.month).padStart(2,'0')} cerrado`)
    },
    onError: e => toast.error(extractErr(e, 'Error al cerrar período')),
  })
  const { mutate: reopenPeriodMut } = useMutation({
    mutationFn: ({ year, month }: { year: number; month: number }) => revenueRecognitionApi.reopenPeriod(year, month),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['asc606-period-closes'] }); toast.success('Período reabierto') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: runMonthly, isPending: runningMonthly } = useMutation({
    mutationFn: (d: RunMonthlyPayload) => revenueRecognitionApi.runMonthly(d),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['asc606-dashboard', dashYear] })
      const r = res.data.recognized
      toast.success(`Reconocimiento completado: T&M ${fmt(r?.over_time)}, línea recta ${fmt(r?.straight_line)}, por avance ${fmt(r?.percentage_complete)}, al cierre ${fmt(r?.completed_contract)}`)
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const asc606ChartData = (asc606Dashboard?.by_month || []).map(m => ({
    mes: MONTHS[m.month - 1],
    Reconocido: Math.round(Number(m.recognized) || 0),
    Diferido:   Math.round(Number(m.deferred) || 0),
    Unbilled:   Math.round(Number(m.unbilled) || 0),
  }))

  const TABS = [
    { id:'asc606',  label:'Contratos ASC 606' },
    { id:'entries', label:'Entradas contables' },
    { id:'info',    label:'ASC 606 / IFRS 15' },
  ]

  const closedPeriodKeys = new Set(periodCloses.map(pc => `${pc.period_year}-${pc.period_month}`))

  return (
    <PageShell>
      <PageHeader icon={<TrendingUp size={18} />} title={t('profitability.revenue')} subtitle={t('profitability.revenue_subtitle')} />

      {/* KPIs */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(min(150px, 100%), 1fr))', gap:14, marginBottom:28 }}>
        {[
          { label:`Reconocido ${dashYear}`, value:fmt(asc606Dashboard?.total_recognized), icon:'✅' },
          { label:`Diferido ${dashYear}`,   value:fmt((asc606Dashboard?.by_month || []).reduce((a, m) => a + (Number(m.deferred) || 0), 0)), icon:'⏳' },
          { label:'Contratos activos', value:asc606Dashboard?.contracts?.length || 0, icon:'📑' },
          { label:'Entradas registradas', value:asc606Dashboard?.entry_count || 0, icon:'📋' },
        ].map((k,i) => (
          <div key={i} style={{ background:'var(--surface-2)', borderRadius:'var(--radius-md)', padding:'16px 18px' }}>
            <div style={{ fontSize: "var(--text-xl)", marginBottom:6 }}>{k.icon}</div>
            <div style={{ fontSize: "var(--text-xl-em)", fontWeight:500, marginBottom:2 }}>{k.value}</div>
            <div className="u-text2-sm">{k.label}</div>
          </div>
        ))}
      </div>

      {/* Tab nav */}
      <div style={{ display:'flex', flexWrap:'wrap', gap:8, marginBottom:24 }}>
        {TABS.map(tb => (
          <button key={tb.id} onClick={() => setTab(tb.id)}
            style={{ padding:'8px 16px', borderRadius:8, border:`.5px solid ${tab===tb.id?'rgba(0,212,255,0.25)':'var(--surface-4)'}`, background:tab===tb.id?'var(--accent-muted)':'transparent', color:tab===tb.id?'var(--accent)':'var(--text-2)', fontSize: "var(--text-base)", fontWeight:500, cursor:'pointer', fontFamily:'inherit' }}>
            {tb.label}
          </button>
        ))}
      </div>

      {/* ── ASC 606 Contratos (nuevo motor) ── */}
      {tab === 'asc606' && (
        <div className="u-stack-20">
          {/* Top bar */}
          <div style={{ display:'flex', flexWrap:'wrap', gap:10, alignItems:'center', justifyContent:'space-between' }}>
            <div style={{ display:'flex', flexWrap:'wrap', gap:10, alignItems:'center' }}>
              <select value={dashYear} onChange={e => setDashYear(Number(e.target.value))} style={{ ...fs, width:'auto' }}>
                {[currentYear-1, currentYear, currentYear+1].map(y => <option key={y} value={y}>{y}</option>)}
              </select>
              <Button variant="secondary" onClick={() => mesAEjecutar && runMonthly({ year: dashYear, month: mesAEjecutar })} disabled={runningMonthly || !mesAEjecutar}
                title={mesAEjecutar ? undefined : 'Ese ejercicio aún no tiene ningún mes terminado'}>
                <RefreshCw size={13} style={{ marginRight:4 }} />{runningMonthly ? 'Procesando...' : `Ejecutar reconocimiento${mesAEjecutar ? ` · ${dashYear}-${String(mesAEjecutar).padStart(2, '0')}` : ''}`}
              </Button>
            </div>
            <div className="u-wrap-10">
              <Button variant="secondary" onClick={() => setShowCloseModal(true)}><Lock size={13} style={{ marginRight:4 }} />{t('revenue.cerrar_periodo')}</Button>
              <Button onClick={() => setShowCreateContract(true)}>{t('revenue.nuevo_contrato')}</Button>
            </div>
          </div>

          {/* Dashboard KPIs */}
          {asc606Dashboard && (
            <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(min(150px, 100%), 1fr))', gap:12 }}>
              {[
                { label:'Total reconocido', value: fmt(asc606Dashboard.total_recognized), icon:'✅' },
                { label:'Contratos activos', value: asc606Dashboard.contracts?.length || 0, icon:'📑' },
                { label:'Entradas contables', value: asc606Dashboard.entry_count || 0, icon:'📋' },
              ].map((k,i) => (
                <div key={i} style={{ background:'var(--surface-2)', borderRadius:'var(--radius-md)', padding:'14px 16px' }}>
                  <div style={{ fontSize: "var(--text-lg-em)", marginBottom:4 }}>{k.icon}</div>
                  <div style={{ fontSize: "var(--text-xl)", fontWeight:500, marginBottom:2 }}>{k.value}</div>
                  <div className="u-text2-xs">{k.label}</div>
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
                  <YAxis tickFormatter={v => fmtMoneda(v, { compacto: true })} tick={{ fontSize: "var(--text-xs)" }} />
                  <Tooltip formatter={(v: number, n: string) => [fmt(v), n]} />
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
              <div className="u-wrap-8">
                {periodCloses.map(pc => (
                  <div key={pc.id} style={{ display:'flex', alignItems:'center', gap:6, padding:'4px 10px', borderRadius:'var(--radius-sm)', background:'var(--surface-2)', fontSize: "var(--text-sm)" }}>
                    <Lock size={11} style={{ color:'var(--accent)' }} />
                    <span>{pc.period_year}-{String(pc.period_month).padStart(2,'0')}</span>
                    <button aria-label={t('revenue.reabrir_periodo')}
                      onClick={() => reopenPeriodMut({ year: pc.period_year, month: pc.period_month })}
                      style={{ background:'none', border:'none', cursor:'pointer', color:'var(--text-3)', padding:0, lineHeight:1 }}
                      title={t('revenue.reabrir_periodo')}
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
            <div style={{ fontSize: "var(--text-sm)", fontWeight:500, marginBottom:10, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'.06em' }}>{t('revenue.contratos_de_reconocimiento')}</div>
            {contractsLoading ? <Spinner /> : contracts.length === 0 ? (
              <EmptyState icon="📑" title={t('revenue.sin_contratos_asc_606')} description="Crea un contrato para configurar el reconocimiento de ingresos por proyecto" />
            ) : (
              <div className="u-stack-10">
                {contracts.map(c => {
                  const mCfg = ASC_METHOD_CFG[c.method] || { label: c.method, icon:'•' }
                  return (
                    <div key={c.id} style={{ ...card, padding:'14px 18px' }}>
                      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
                        <div className="u-flex1-min0">
                          <div style={{ display:'flex', flexWrap:'wrap', gap:8, alignItems:'center', marginBottom:6 }}>
                            <span style={{ fontSize: "var(--text-md)", fontWeight:500 }}>{c.name}</span>
                            <span style={{ fontSize: "var(--text-xs)", padding:'1px 6px', borderRadius:4, background:'var(--accent-muted)', color:'var(--accent)' }}>
                              {mCfg.icon} {mCfg.label}
                            </span>
                            {!c.is_active && (
                              <span style={{ fontSize: "var(--text-xs)", padding:'1px 6px', borderRadius:4, background:'var(--surface-3)', color:'var(--text-3)' }}>Inactivo</span>
                            )}
                          </div>
                          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(min(110px, 100%), 1fr))', gap:16, marginBottom:10 }}>
                            <div><div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginBottom:1 }}>Valor contrato</div><div style={{ fontSize: "var(--text-base)", fontWeight:500 }}>{fmt(c.contract_value)}</div></div>
                            <div><div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginBottom:1 }}>Moneda</div><div style={{ fontSize: "var(--text-base)" }}>{c.currency}</div></div>
                            <div><div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginBottom:1 }}>Inicio</div><div style={{ fontSize: "var(--text-base)" }}>{c.start_date || '—'}</div></div>
                            <div><div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginBottom:1 }}>Fin</div><div style={{ fontSize: "var(--text-base)" }}>{c.end_date || c.duration_months ? `${c.duration_months}m` : '—'}</div></div>
                          </div>
                          <button onClick={() => setObligationsFor(c.id)}
                            style={{ fontSize: "var(--text-xs)", padding:'3px 10px', borderRadius:'var(--radius-sm)', border:'.5px solid var(--surface-4)', background:'transparent', color:'var(--text-2)', cursor:'pointer', fontFamily:'inherit' }}>
                            {t('revenue.obligaciones_de_desempeno_2')}
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
        <div className="u-stack-16">
          {/* Filters */}
          <div style={{ display:'flex', flexWrap:'wrap', gap:10, alignItems:'flex-end' }}>
            <div style={{ flex:'1 1 220px', minWidth:0 }}>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Contrato</label>
              <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={entryFilter.contract_id} onChange={e => setEntryFilter(f=>({...f, contract_id:e.target.value}))} style={fs}>
                <option value="">{t('revenue.todos_los_contratos')}</option>
                {contracts.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('revenue.ano')}</label>
              <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={entryFilter.year} onChange={e => setEntryFilter(f=>({...f, year:e.target.value}))} style={{...fs, width:100}}>
                <option value="">{t('revenue.todos')}</option>
                {[currentYear-1, currentYear, currentYear+1].map(y => <option key={y} value={y}>{y}</option>)}
              </select>
            </div>
            <div>
              <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>Mes</label>
              <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={entryFilter.month} onChange={e => setEntryFilter(f=>({...f, month:e.target.value}))} style={{...fs, width:110}}>
                <option value="">{t('revenue.todos')}</option>
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
            <EmptyState icon="📋" title={t('revenue.sin_entradas_contables')} description="Las entradas se generan al ejecutar el reconocimiento mensual" />
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
                    const mCfg = ASC_METHOD_CFG[e.method ?? ''] || { label:e.method||'—', icon:'•' }
                    const isReversed = e.is_reversed
                    // Una entrada de reversión no se revierte (el servidor responde 400).
                    const esReversion = e.entry_type === 'reversal'
                    const esDiferido = e.entry_type === 'deferred'
                    return (
                      <tr key={e.id} style={{ borderBottom:'1px solid var(--surface-4)', background: idx%2===0?'transparent':'rgba(255,255,255,0.02)', opacity: isReversed ? 0.5 : 1 }}>
                        <td style={{ padding:'10px 14px' }}>
                          <div style={{ fontWeight:500 }}>{e.contract_name || e.rev_contract_id}</div>
                          {e.description && <div className="u-text3-xs">{e.description}</div>}
                        </td>
                        <td style={{ padding:'10px 14px', fontFamily:'var(--font-mono)', fontSize: "var(--text-sm)" }}>
                          {e.period_year}-{String(e.period_month).padStart(2,'0')}
                        </td>
                        <td style={{ padding:'10px 14px', textAlign:'center' }}>
                          <span className="u-xs">{mCfg.icon} {mCfg.label}</span>
                        </td>
                        <td style={{ padding:'10px 14px', textAlign:'center', fontWeight:600, color:'var(--success)' }}>
                          {fmt(esDiferido ? 0 : e.amount)}
                        </td>
                        <td style={{ padding:'10px 14px', textAlign:'center', color:'var(--warning)' }}>
                          {fmt(esDiferido ? e.amount : 0)}
                        </td>
                        <td style={{ padding:'10px 14px', textAlign:'center' }}>
                          {isReversed
                            ? <span style={{ fontSize: "var(--text-xs)", color:'var(--danger)' }}>Revertida</span>
                            : esReversion
                            ? <span className="u-text3-xs">Reversión</span>
                            : <span style={{ fontSize: "var(--text-xs)", color:'var(--success)' }}>Activa</span>}
                        </td>
                        <td style={{ padding:'10px 14px', textAlign:'center' }}>
                          {!isReversed && !esReversion && (
                            <button onClick={() => { openConfirmGlobal({ message: '¿Revertir esta entrada? Esta acción no se puede deshacer.', onConfirm: () => reverseEntry(e.id), danger: true }) }}
                              style={{ fontSize: "var(--text-xs)", padding:'3px 9px', borderRadius:'var(--radius-sm)', border:'1px solid rgba(239,68,68,0.3)', background:'transparent', color:'var(--danger)', cursor:'pointer', fontFamily:'inherit' }}>
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
          <div style={{ fontSize: "var(--text-md)", fontWeight:500, marginBottom:16 }}>{t('revenue.asc_606_ifrs_15_los_5_pasos')}</div>
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
                <div className="u-text2-sm">{desc}</div>
              </div>
            </div>
          ))}
          <div style={{ marginTop:16, display:'flex', flexDirection:'column', gap:10 }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight:500 }}>{t('revenue.metodos_disponibles')}</div>
            {Object.entries(ASC_METHOD_CFG).map(([k, v]) => (
              <div key={k} style={{ display:'flex', gap:10, padding:'8px 12px', background:'var(--surface-2)', borderRadius:8 }}>
                <span style={{ fontSize: "var(--text-lg)" }}>{v.icon}</span>
                <div>
                  <div style={{ fontSize: "var(--text-sm)", fontWeight:500 }}>{v.label}</div>
                  <div className="u-text2-xs">{v.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Modal nuevo contrato ASC 606 ── */}
      {showCreateContract && (
        <Modal open title={t('revenue.nuevo_contrato_asc_606')} onClose={() => setShowCreateContract(false)} width={540}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>Proyecto</label>
              <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={contractForm.project_id} onChange={e=>setContractForm(f=>({...f,project_id:e.target.value}))} style={fs}>
                <option value="">Seleccionar proyecto...</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
              </select>
            </div>
            <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={ls}>{t('revenue.nombre_del_contrato')}</label>
              <input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={contractForm.name} onChange={e=>setContractForm(f=>({...f,name:e.target.value}))} style={fs} placeholder="Ej: Contrato desarrollo Q1 2026" />
            </div>
            <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={ls}>{t('revenue.metodo_de_reconocimiento')}</label>
              <select id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={contractForm.method} onChange={e=>setContractForm(f=>({...f,method:e.target.value}))} style={fs}>
                {Object.entries(ASC_METHOD_CFG).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label} — {v.desc}</option>)}
              </select>
            </div>
            <div className="u-grid2-12">
              <div><label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} style={ls}>{t('revenue.valor_del_contrato_2')}</label>
                <input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} type="number" value={contractForm.contract_value} onChange={e=>setContractForm(f=>({...f,contract_value:e.target.value}))} style={fs} placeholder="50000" />
              </div>
              <div><label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} style={ls}>Moneda</label>
                <select id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} value={contractForm.currency} onChange={e=>setContractForm(f=>({...f,currency:e.target.value}))} style={fs}>
                  {monedasDeLaEmpresa.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            </div>
            <div className="u-grid2-12">
              <div><label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} style={ls}>Fecha inicio</label><DateInput id={`${idCampo}-9`} value={contractForm.start_date} onChange={e=>setContractForm(f=>({...f,start_date:e.target.value}))} style={fs} /></div>
              <div><label id={`${idCampo}-et10`} htmlFor={`${idCampo}-10`} style={ls}>Fecha fin</label><DateInput id={`${idCampo}-10`} value={contractForm.end_date} onChange={e=>setContractForm(f=>({...f,end_date:e.target.value}))} style={fs} /></div>
            </div>
            {contractForm.method === 'straight_line' && (
              <div><label id={`${idCampo}-et11`} htmlFor={`${idCampo}-11`} style={ls}>{t('revenue.duracion_meses_alternativa_a_fecha_fin')}</label>
                <input id={`${idCampo}-11`} aria-labelledby={`${idCampo}-et11`} type="number" value={contractForm.duration_months} onChange={e=>setContractForm(f=>({...f,duration_months:e.target.value}))} style={fs} placeholder="12" />
              </div>
            )}
            <div><label id={`${idCampo}-et12`} htmlFor={`${idCampo}-12`} style={ls}>Notas</label>
              <textarea id={`${idCampo}-12`} aria-labelledby={`${idCampo}-et12`} value={contractForm.notes} onChange={e=>setContractForm(f=>({...f,notes:e.target.value}))} rows={2} style={{...fs,resize:'vertical'}} />
            </div>
            <div className="u-actions-10">
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
        <Modal open title={t('revenue.cerrar_periodo_contable')} onClose={() => setShowCloseModal(false)} width={420}>
          <div className="u-stack-14">
            <div style={{ background:'var(--warning-bg)', borderRadius:8, padding:'10px 12px', fontSize: "var(--text-sm)", color:'var(--warning)' }}>
              {t('revenue.una_vez_cerrado_no_se_podran_crear')}
            </div>
            <div className="u-grid2-12">
              <div><label id={`${idCampo}-et13`} htmlFor={`${idCampo}-13`} style={ls}>{t('revenue.ano')}</label>
                <input id={`${idCampo}-13`} aria-labelledby={`${idCampo}-et13`} type="number" value={closePeriod.year} onChange={e=>setClosePeriod(p=>({...p,year:parseInt(e.target.value)}))} style={fs} />
              </div>
              <div><label id={`${idCampo}-et14`} htmlFor={`${idCampo}-14`} style={ls}>Mes</label>
                <select id={`${idCampo}-14`} aria-labelledby={`${idCampo}-et14`} value={closePeriod.month} onChange={e=>setClosePeriod(p=>({...p,month:parseInt(e.target.value)}))} style={fs}>
                  {MONTHS.map((m,i) => <option key={i+1} value={i+1}>{i+1} — {m}</option>)}
                </select>
              </div>
            </div>
            {closedPeriodKeys.has(`${closePeriod.year}-${closePeriod.month}`) && (
              <div style={{ fontSize: "var(--text-sm)", color:'var(--danger)', padding:'6px 10px', background:'var(--danger-bg)', borderRadius:'var(--radius-sm)' }}>
                {t('revenue.este_periodo_ya_esta_cerrado')}
              </div>
            )}
            <div><label id={`${idCampo}-et15`} htmlFor={`${idCampo}-15`} style={ls}>Notas (opcional)</label>
              <textarea id={`${idCampo}-15`} aria-labelledby={`${idCampo}-et15`} value={closePeriod.notes} onChange={e=>setClosePeriod(p=>({...p,notes:e.target.value}))} rows={2} style={{...fs,resize:'vertical'}} />
            </div>
            <div className="u-actions-10">
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
