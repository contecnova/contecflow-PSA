/**
 * RevenuePage — Reconocimiento de ingresos ASC 606 / IFRS 15
 * Configura el método por proyecto y registra entradas mensuales
 *
 * 16-11-2026: pasada de diseño. Título como el menú ("Reconocimiento de
 * ingresos"); "Nuevo contrato" a la cabecera con icono; KPIs con KpiCard e
 * icono lucide (antes emojis y una segunda fila que repetía los mismos
 * datos); pestañas con Tabs (antes botones propios más grandes); métodos
 * con icono lucide (antes emojis); gráfico vacío con EmptyState (antes una
 * tarjeta grande en blanco); campos con .ds-input; botones del kit en lugar
 * de los símbolos de texto; sin ancho máximo en la pestaña de información.
 */
import { useState, useId, type ReactNode } from 'react'
import { extractErr, fmtDate, localeActivo } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { revenueRecognitionApi } from '../services/api'
import type { CierreAsc606, ContratoAsc606, EntradaAsc606DelDiario, ObligacionAsc606, PanelAsc606 } from '../services/api/tipos-finanzas'
import type { MetaDeLista } from '../services/api/tipos-plataforma'
import { Button, Card, KpiCard, Modal, Spinner, EmptyState, Tabs, IconButton, Select, TablaSimple, useErroresDeCampo, Input, Textarea } from '../components/ui'
import Pagination from '../components/ui/Pagination'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { BarChart3, BookOpen, CheckCircle2, Circle, ClipboardList, Clock, FileText, Flag, Hourglass, Info, Layers, ListChecks, Lock, LockOpen, Pencil, Percent, Plus, RefreshCw, Trash2, TrendingUp, Undo2, X } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'
import { useOrgSettings } from '../hooks/useOrgSettings'
import { openConfirmGlobal } from '../context/ConfirmContext'
import DateInput from '../components/ui/DateInput'
import { DEFAULT_PAGE_SIZE } from '../constants/pagination'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { useListaDeProyectos } from '../hooks/useListas'
import './RevenuePage.css'

type T = ReturnType<typeof useAppT>
type MethodCfg = { label: string; desc?: string; icon: ReactNode }

// Métodos del motor ASC 606 (icono lucide fijo; textos traducidos).
const ASC_METHOD_ICONS: Record<string, ReactNode> = {
  over_time: <Clock size={13} aria-hidden />,
  milestone: <Flag size={13} aria-hidden />,
  consumption: <Layers size={13} aria-hidden />,
  straight_line: <TrendingUp size={13} aria-hidden />,
  percentage_complete: <Percent size={13} aria-hidden />,
  completed_contract: <CheckCircle2 size={13} aria-hidden />,
}
const ASC_METHODS = Object.keys(ASC_METHOD_ICONS)

function metodo(t: T, m: string | null | undefined): MethodCfg {
  if (m && ASC_METHOD_ICONS[m]) {
    return { label: t(`revenue_page.metodo_${m}`), desc: t(`revenue_page.metodo_${m}_desc`), icon: ASC_METHOD_ICONS[m] }
  }
  return { label: m || '—', icon: <Circle size={13} aria-hidden /> }
}

/** Nombres cortos de los meses en el idioma activo. */
function nombresDeMes(): string[] {
  const f = new Intl.DateTimeFormat(localeActivo(), { month: 'short' })
  return Array.from({ length: 12 }, (_, i) => f.format(new Date(2000, i, 1)))
}

type Obligation = ObligacionAsc606

type ObligationPayload = { name: string; method: string; standalone_price: number; notes: string }

type RevenueContract = ContratoAsc606

type RevenueEntry = EntradaAsc606DelDiario

type PeriodClose = CierreAsc606

type Asc606Dashboard = PanelAsc606

type ContractPayload = {
  project_id: string; name: string; method: string; contract_value: number; currency: string
  start_date: string; end_date: string; duration_months: number | null; notes: string
}
type ClosePeriodPayload = { year: number; month: number; notes: string | null }
type RunMonthlyPayload = { year: number; month: number }
type EntryParams = { contract_id?: string; year?: string; month?: string; page: number; page_size: number }
type PaginaDeEntradas = { items: RevenueEntry[]; total: number }

const ENTRIES_PAGE_SIZE = DEFAULT_PAGE_SIZE
const periodo = (y: number, m: number) => `${y}-${String(m).padStart(2, '0')}`

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

  const camposB = useErroresDeCampo()
  const msgB = (k: string) => camposB.de(k) ? <div className="u-field-error">{camposB.de(k)}</div> : null
  const { mutate: save, isPending: saving } = useMutation({
    onMutate: () => camposB.limpiar(),
    mutationFn: (d: ObligationPayload) => editing
      ? revenueRecognitionApi.updateObligation(editing.id, d).then(r => r.data)
      : revenueRecognitionApi.createObligation(contractId, d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['asc606-obligations', contractId] }); reset() },
    onError: (e: unknown) => { if (!camposB.recoger(e)) toast.error(extractErr(e, t('revenue_page.error_guardar_obligacion'))) },
  })

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => revenueRecognitionApi.deleteObligation(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['asc606-obligations', contractId] }),
    onError: e => toast.error(extractErr(e, t('revenue_page.error_generico'))),
  })

  return (
    <Modal open onClose={onClose} title={t('revenue.obligaciones_de_desempeno')} width={560}>
      <div className="u-stack-12">
        {isLoading ? <Spinner /> : obs.length === 0 && !showForm ? (
          <EmptyState icon={<ListChecks size={28} />} title={t('revenue.sin_obligaciones')} description={t('revenue_page.sin_obligaciones_desc')} />
        ) : (
          <div className="u-stack-8">
            {obs.map(ob => {
              const mCfg = metodo(t, ob.method)
              return (
                <div key={ob.id} className="rev-ob">
                  <div className="u-flex1-min0">
                    <div className="rev-ob__name">{ob.name}</div>
                    <div className="u-text2-xs-mt2 rev-metodo">
                      {mCfg.icon} {mCfg.label}
                      {(ob.standalone_price ?? 0) > 0 && <span className="rev-ob__extra">{fmtEur(ob.standalone_price ?? 0, currency)}</span>}
                      {ob.is_satisfied && <span className="rev-ob__done"><CheckCircle2 size={12} aria-hidden /> {t('revenue_page.completada')}</span>}
                    </div>
                  </div>
                  <div className="rev-ob__actions">
                    <IconButton variante="caja" type="button"
                      ariaLabel={t('revenue_page.editar_obligacion', { nombre: ob.name })} title={t('revenue_page.editar')}
                      onClick={() => { setEditing(ob); setForm({ name:ob.name, method:ob.method||'over_time', standalone_price:String(ob.standalone_price||''), notes:ob.notes||'' }); setShowForm(true) }}>
                      <Pencil size={14} aria-hidden />
                    </IconButton>
                    <IconButton variante="caja" tono="peligro" type="button"
                      ariaLabel={t('revenue_page.borrar_obligacion', { nombre: ob.name })} title={t('revenue_page.borrar')}
                      onClick={() => openConfirmGlobal({ message: t('revenue_page.confirmar_borrar_obligacion', { nombre: ob.name }), danger: true, onConfirm: () => del(ob.id) })}>
                      <Trash2 size={14} aria-hidden />
                    </IconButton>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {showForm ? (
          <div className="rev-ob-form">
            <div className="u-grid2-10">
              <div>
                <Input label={t('revenue_page.nombre')} id={`${idCampo}-1`} value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} placeholder={t('revenue.ej_fase_1_analisis')} />{msgB('name')}
              </div>
              <div>
                <Select label={t('revenue.metodo')} placeholder={false} id={`${idCampo}-2`} value={form.method} onChange={e=>setForm(f=>({...f,method:e.target.value}))}>
                  {ASC_METHODS.map(k => { const v = metodo(t, k); return <option key={k} value={k}>{v.label}</option> })}
                </Select>{msgB('method')}
              </div>
            </div>
            <div>
              <Input label={t('revenue_page.precio_independiente')} id={`${idCampo}-3`} type="number" value={form.standalone_price} onChange={e=>setForm(f=>({...f,standalone_price:e.target.value}))} placeholder="0" />{msgB('standalone_price')}
            </div>
            <div>
              <Textarea label={t('revenue_page.notas')} id={`${idCampo}-4`} value={form.notes} onChange={e=>setForm(f=>({...f,notes:e.target.value}))} rows={2} />{msgB('notes')}
            </div>
            <div className="u-actions-8">
              <Button variant="secondary" onClick={reset}>{t('revenue_page.cancelar')}</Button>
              <Button onClick={() => save({ ...form, standalone_price: parseFloat(form.standalone_price)||0 })} disabled={!form.name.trim()} loading={saving}>
                {editing ? t('revenue_page.guardar') : t('revenue_page.anadir')}
              </Button>
            </div>
          </div>
        ) : (
          <div>
            <Button variant="secondary" icon={<Plus size={14} />} onClick={() => setShowForm(true)}>{t('revenue.anadir_obligacion')}</Button>
          </div>
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
  const MONTHS = nombresDeMes()
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
  const [entryPage, setEntryPage] = useState(1)
  const [closePeriod, setClosePeriod] = useState({ year: cerradoY, month: cerradoM, notes: '' })
  const [contractForm, setContractForm] = useState({ project_id:'', name:'', method:'over_time', contract_value:'', currency, start_date:'', end_date:'', duration_months:'', notes:'' })

  // Cambiar un filtro vuelve a la primera página.
  const filtrarEntradas = (cambio: Partial<typeof entryFilter>) => {
    setEntryFilter(f => ({ ...f, ...cambio }))
    setEntryPage(1)
  }

  // `projectsApi.list` recorre todas las páginas y devuelve siempre el array.
  const { data: projects = [] } = useListaDeProyectos()

  // ── New ASC 606 queries ────────────────────────────────────────────────────
  const { data: asc606Dashboard } = useQuery<Asc606Dashboard>({
    queryKey: ['asc606-dashboard', dashYear],
    queryFn: () => revenueRecognitionApi.dashboard(dashYear, undefined).then(r => r.data),
  })
  const { data: contracts = [], isLoading: contractsLoading } = useQuery<RevenueContract[]>({
    queryKey: ['asc606-contracts'],
    queryFn: () => revenueRecognitionApi.contracts(undefined).then(r => r.data),
    enabled: tab === 'asc606' || tab === 'entries',
  })
  const { data: periodCloses = [] } = useQuery<PeriodClose[]>({
    queryKey: ['asc606-period-closes'],
    queryFn: () => revenueRecognitionApi.periodCloses().then(r => r.data),
    enabled: tab === 'asc606',
  })

  // Listado paginado en el servidor (page/page_size; total en meta.total).
  const { data: paginaDeEntradas, isLoading: entriesLoading } = useQuery<PaginaDeEntradas>({
    queryKey: ['asc606-entries', entryFilter, entryPage],
    queryFn: () => {
      const p: EntryParams = { page: entryPage, page_size: ENTRIES_PAGE_SIZE }
      if (entryFilter.contract_id) p.contract_id = entryFilter.contract_id
      if (entryFilter.year)        p.year         = entryFilter.year
      if (entryFilter.month)       p.month        = entryFilter.month
      return revenueRecognitionApi.entries(p)
        .then(r => {
          const meta = (r as typeof r & { meta?: MetaDeLista }).meta
          return { items: r.data, total: meta?.total ?? r.data.length }
        })
    },
    enabled: tab === 'entries',
    placeholderData: keepPreviousData,
  })
  const entries = paginaDeEntradas?.items ?? []
  const entriesTotal = paginaDeEntradas?.total ?? 0
  const entriesTotalPages = Math.max(1, Math.ceil(entriesTotal / ENTRIES_PAGE_SIZE))

  const { mutate: reverseEntry } = useMutation({
    mutationFn: (id: string) => revenueRecognitionApi.reverseEntry(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['asc606-entries'] }); toast.success(t('revenue_page.entrada_revertida')) },
    onError: e => toast.error(extractErr(e, t('revenue_page.error_revertir'))),
  })

  // ── New ASC 606 mutations ──────────────────────────────────────────────────
  const { mutate: createContract, isPending: creatingContract } = useMutation({
    mutationFn: (d: ContractPayload) => revenueRecognitionApi.createContract(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['asc606-contracts'] })
      qc.invalidateQueries({ queryKey: ['asc606-dashboard', dashYear] })
      setShowCreateContract(false)
      toast.success(t('revenue_page.contrato_creado'))
    },
    onError: e => toast.error(extractErr(e, t('revenue_page.error_crear_contrato'))),
  })
  const { mutate: closePeriodMut, isPending: closingPeriod } = useMutation({
    mutationFn: (d: ClosePeriodPayload) => revenueRecognitionApi.closePeriod(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['asc606-period-closes'] })
      setShowCloseModal(false)
      toast.success(t('revenue_page.periodo_cerrado', { periodo: periodo(closePeriod.year, closePeriod.month) }))
    },
    onError: e => toast.error(extractErr(e, t('revenue_page.error_cerrar_periodo'))),
  })
  const { mutate: reopenPeriodMut } = useMutation({
    mutationFn: ({ year, month }: { year: number; month: number }) => revenueRecognitionApi.reopenPeriod(year, month),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['asc606-period-closes'] }); toast.success(t('revenue_page.periodo_reabierto')) },
    onError: e => toast.error(extractErr(e, t('revenue_page.error_generico'))),
  })
  const { mutate: runMonthly, isPending: runningMonthly } = useMutation({
    mutationFn: (d: RunMonthlyPayload) => revenueRecognitionApi.runMonthly(d),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['asc606-dashboard', dashYear] })
      const r = res.data.recognized
      toast.success(t('revenue_page.reconocimiento_completado', {
        tm: fmt(r?.over_time), linea: fmt(r?.straight_line), avance: fmt(r?.percentage_complete), cierre: fmt(r?.completed_contract),
      }))
    },
    onError: e => toast.error(extractErr(e, t('revenue_page.error_generico'))),
  })

  const asc606ChartData = (asc606Dashboard?.by_month || []).map(m => ({
    mes: MONTHS[m.month - 1],
    recognized: Math.round(Number(m.recognized) || 0),
    deferred:   Math.round(Number(m.deferred) || 0),
    unbilled:   Math.round(Number(m.unbilled) || 0),
  }))

  const TABS = [
    { id:'asc606',  label: t('revenue_page.tab_contratos'), icon: <FileText size={14} /> },
    { id:'entries', label: t('revenue_page.tab_entradas'),  icon: <BookOpen size={14} /> },
    { id:'info',    label: t('revenue_page.tab_info'),      icon: <Info size={14} /> },
  ]
  // El gráfico solo tiene sentido si algún mes tiene importes.
  const graficoConDatos = asc606ChartData.some(m => m.recognized || m.deferred || m.unbilled)

  const PASOS = [1, 2, 3, 4, 5].map(n => [t(`revenue_page.paso_${n}`), t(`revenue_page.paso_${n}_desc`)])

  const COLUMNAS = [
    t('revenue_page.col_contrato'), t('revenue_page.col_periodo'), t('revenue_page.col_metodo'),
    t('revenue_page.col_reconocido'), t('revenue_page.col_diferido'), t('revenue_page.col_estado'), '',
  ]

  const closedPeriodKeys = new Set(periodCloses.map(pc => `${pc.period_year}-${pc.period_month}`))

  return (
    <PageShell>
      <PageHeader icon={<TrendingUp size={18} />} title={t('nav.revenue')} subtitle={t('profitability.revenue_subtitle')}
        actions={<Button icon={<Plus size={14} />} onClick={() => setShowCreateContract(true)}>{t('revenue.nuevo_contrato')}</Button>} />

      {/* KPIs (una sola fila: antes se repetían en la pestaña de contratos) */}
      <div className="ds-grid-stats rev-kpis">
        <KpiCard icon={<CheckCircle2 size={16} />} label={t('revenue_page.kpi_reconocido', { anio: dashYear })} value={fmt(asc606Dashboard?.total_recognized)} />
        <KpiCard icon={<Hourglass size={16} />} label={t('revenue_page.kpi_diferido', { anio: dashYear })}
          value={fmt((asc606Dashboard?.by_month || []).reduce((a, m) => a + (Number(m.deferred) || 0), 0))} />
        <KpiCard icon={<FileText size={16} />} label={t('revenue_page.kpi_contratos_activos')} value={asc606Dashboard?.contracts?.length || 0} />
        <KpiCard icon={<ClipboardList size={16} />} label={t('revenue_page.kpi_entradas_registradas')} value={asc606Dashboard?.entry_count || 0} />
      </div>

      <Tabs items={TABS} active={tab} onChange={setTab} ariaLabel={t('revenue_page.secciones')} className="rev-tabs" />

      {/* ── ASC 606 Contratos (nuevo motor) ── */}
      {tab === 'asc606' && (
        <div className="u-stack-20">
          {/* Top bar */}
          <div className="rev-topbar">
            <div className="rev-topbar__group">
              <Select suelto placeholder={false} value={dashYear} onChange={e => setDashYear(Number(e.target.value))} className="rev-input--auto"
                aria-label={t('revenue_page.ejercicio')}>
                {[currentYear-1, currentYear, currentYear+1].map(y => <option key={y} value={y}>{y}</option>)}
              </Select>
              <Button variant="secondary" icon={<RefreshCw size={14} />} onClick={() => mesAEjecutar && runMonthly({ year: dashYear, month: mesAEjecutar })} disabled={runningMonthly || !mesAEjecutar}
                title={mesAEjecutar ? undefined : t('revenue_page.sin_mes_terminado')}>
                {runningMonthly
                  ? t('revenue_page.procesando')
                  : mesAEjecutar
                    ? t('revenue_page.ejecutar_reconocimiento_periodo', { periodo: periodo(dashYear, mesAEjecutar) })
                    : t('revenue_page.ejecutar_reconocimiento')}
              </Button>
            </div>
            <div className="u-wrap-10">
              <Button variant="secondary" icon={<Lock size={14} />} onClick={() => setShowCloseModal(true)}>{t('revenue.cerrar_periodo')}</Button>
            </div>
          </div>

          {/* Chart */}
          {asc606Dashboard && !graficoConDatos && (
            <Card>
              <EmptyState icon={<BarChart3 size={28} />} title={t('revenue_page.grafico_vacio_titulo', { anio: dashYear })}
                description={t('revenue_page.grafico_vacio_desc')} />
            </Card>
          )}
          {graficoConDatos && (
            <div className="rev-card rev-card--chart">
              <div className="rev-title">{t('revenue_page.grafico_titulo', { anio: dashYear })}</div>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={asc606ChartData}>
                  <XAxis dataKey="mes" tick={{ fontSize: "var(--text-xs)" }} />
                  <YAxis tickFormatter={v => fmtMoneda(v, { compacto: true })} tick={{ fontSize: "var(--text-xs)" }} />
                  <Tooltip formatter={(v: number, n: string) => [fmt(v), n]} />
                  <Legend />
                  <Bar dataKey="recognized" name={t('revenue_page.serie_reconocido')} fill="var(--success)" radius={[3,3,0,0]} />
                  <Bar dataKey="deferred"   name={t('revenue_page.serie_diferido')} fill="var(--warning)" radius={[3,3,0,0]} />
                  <Bar dataKey="unbilled"   name={t('revenue_page.serie_sin_facturar')} fill="var(--accent)" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Period closes */}
          {periodCloses.length > 0 && (
            <div className="rev-card rev-card--closes">
              <div className="rev-heading">{t('revenue_page.cierres_contables')}</div>
              <div className="u-wrap-8">
                {periodCloses.map(pc => (
                  <div key={pc.id} className="rev-close">
                    <Lock size={11} className="rev-close__lock" aria-hidden="true" />
                    <span>{periodo(pc.period_year, pc.period_month)}</span>
                    <IconButton type="button" ariaLabel={t('revenue.reabrir_periodo')}
                      onClick={() => reopenPeriodMut({ year: pc.period_year, month: pc.period_month })}
                      className="rev-close__reopen"
                      title={t('revenue.reabrir_periodo')}
                    >
                      <LockOpen size={11} />
                    </IconButton>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Contracts list */}
          <div>
            <div className="rev-heading">{t('revenue.contratos_de_reconocimiento')}</div>
            {contractsLoading ? <Spinner /> : contracts.length === 0 ? (
              <EmptyState icon={<FileText size={28} />} title={t('revenue.sin_contratos_asc_606')} description={t('revenue_page.sin_contratos_desc')}
                action={<Button icon={<Plus size={14} />} onClick={() => setShowCreateContract(true)}>{t('revenue.nuevo_contrato')}</Button>} />
            ) : (
              <div className="u-stack-10">
                {contracts.map(c => {
                  const mCfg = metodo(t, c.method)
                  return (
                    <div key={c.id} className="rev-card rev-card--contract">
                      <div className="rev-contract__row">
                        <div className="u-flex1-min0">
                          <div className="rev-contract__head">
                            <span className="rev-contract__name">{c.name}</span>
                            <span className="rev-tag rev-metodo">{mCfg.icon} {mCfg.label}</span>
                            {!c.is_active && <span className="rev-tag rev-tag--muted">{t('revenue_page.inactivo')}</span>}
                          </div>
                          <dl className="rev-contract__facts">
                            <div><dt className="rev-fact__label">{t('revenue_page.valor_contrato')}</dt><dd className="rev-fact__value rev-fact__value--strong">{fmt(c.contract_value)}</dd></div>
                            <div><dt className="rev-fact__label">{t('revenue_page.moneda')}</dt><dd className="rev-fact__value">{c.currency}</dd></div>
                            <div><dt className="rev-fact__label">{t('revenue_page.inicio')}</dt><dd className="rev-fact__value">{c.start_date ? fmtDate(c.start_date) : '—'}</dd></div>
                            <div><dt className="rev-fact__label">{t('revenue_page.fin')}</dt><dd className="rev-fact__value">
                              {c.end_date ? fmtDate(c.end_date) : c.duration_months ? t('revenue_page.duracion_meses', { n: c.duration_months }) : '—'}
                            </dd></div>
                          </dl>
                          <Button variant="secondary" size="sm" icon={<ListChecks size={14} />} onClick={() => setObligationsFor(c.id)}>
                            {t('revenue.obligaciones_de_desempeno_2')}
                          </Button>
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
          <div className="rev-filters">
            <div className="rev-filters__contract">
              <Select label={t('revenue_page.contrato')} placeholder={false} id={`${idCampo}-1`} value={entryFilter.contract_id} onChange={e => filtrarEntradas({ contract_id: e.target.value })}>
                <option value="">{t('revenue.todos_los_contratos')}</option>
                {contracts.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            </div>
            <Select label={t('revenue.ano')} placeholder={false} id={`${idCampo}-2`} value={entryFilter.year} onChange={e => filtrarEntradas({ year: e.target.value })}>
                <option value="">{t('revenue.todos')}</option>
                {[currentYear-1, currentYear, currentYear+1].map(y => <option key={y} value={y}>{y}</option>)}
              </Select>
            <Select label={t('revenue_page.mes')} placeholder={false} id={`${idCampo}-3`} value={entryFilter.month} onChange={e => filtrarEntradas({ month: e.target.value })}>
                <option value="">{t('revenue.todos')}</option>
                {MONTHS.map((m,i) => <option key={i+1} value={i+1}>{i+1} — {m}</option>)}
              </Select>
            {(entryFilter.contract_id||entryFilter.year||entryFilter.month) && (
              <Button variant="ghost" icon={<X size={14} />} onClick={() => filtrarEntradas({ contract_id:'', year:'', month:'' })}>
                {t('revenue_page.limpiar')}
              </Button>
            )}
          </div>

          {/* Table */}
          {entriesLoading ? <Spinner /> : entries.length === 0 ? (
            <EmptyState icon={<BookOpen size={28} />} title={t('revenue.sin_entradas_contables')} description={t('revenue_page.sin_entradas_desc')} />
          ) : (
            <>
              <div className="rev-card rev-card--table">
                <TablaSimple claseTabla="rev-table">
                  <thead>
                    <tr>
                      {COLUMNAS.map((h,i) => (
                        <th key={i} scope="col" className={i <= 1 ? 'rev-left' : undefined}>
                          {h || <span className="u-sr-only">{t('revenue_page.col_acciones')}</span>}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map(e => {
                      const mCfg = metodo(t, e.method)
                      const isReversed = e.is_reversed
                      // Una entrada de reversión no se revierte (el servidor responde 400).
                      const esReversion = e.entry_type === 'reversal'
                      const esDiferido = e.entry_type === 'deferred'
                      return (
                        <tr key={e.id} className={isReversed ? 'rev-row--reversed' : undefined}>
                          <td className="rev-left">
                            <div className="rev-entry__name">{e.contract_name || e.rev_contract_id}</div>
                            {e.description && <div className="u-text3-xs">{e.description}</div>}
                          </td>
                          <td className="rev-left rev-period">
                            {periodo(e.period_year, e.period_month)}
                          </td>
                          <td>
                            <span className="u-xs rev-metodo">{mCfg.icon} {mCfg.label}</span>
                          </td>
                          <td className="rev-amount--recognized">
                            {fmt(esDiferido ? 0 : e.amount)}
                          </td>
                          <td className="rev-amount--deferred">
                            {fmt(esDiferido ? e.amount : 0)}
                          </td>
                          <td>
                            {isReversed
                              ? <span className="rev-status rev-status--reversed">{t('revenue_page.estado_revertida')}</span>
                              : esReversion
                              ? <span className="u-text3-xs">{t('revenue_page.estado_reversion')}</span>
                              : <span className="rev-status rev-status--active">{t('revenue_page.estado_activa')}</span>}
                          </td>
                          <td>
                            {!isReversed && !esReversion && (
                              <Button variant="secondary" size="sm" icon={<Undo2 size={14} />}
                                onClick={() => { openConfirmGlobal({ message: t('revenue_page.confirmar_revertir'), onConfirm: () => reverseEntry(e.id), danger: true }) }}>
                                {t('revenue_page.revertir')}
                              </Button>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </TablaSimple>
              </div>
              <Pagination page={entryPage} totalPages={entriesTotalPages} onChange={setEntryPage}
                total={entriesTotal} pageSize={ENTRIES_PAGE_SIZE} />
            </>
          )}
        </div>
      )}

      {/* ── Info ASC 606 ── */}
      {tab === 'info' && (
        <Card className="rev-card--info">
          <div className="rev-title">{t('revenue.asc_606_ifrs_15_los_5_pasos')}</div>
          {PASOS.map(([title, desc], i) => (
            <div key={i} className="rev-step">
              <div className="rev-step__num" aria-hidden="true">{i+1}</div>
              <div>
                <div className="rev-step__title">{title}</div>
                <div className="u-text2-sm">{desc}</div>
              </div>
            </div>
          ))}
          <div className="rev-methods">
            <div className="rev-methods__title">{t('revenue.metodos_disponibles')}</div>
            {ASC_METHODS.map(k => {
              const v = metodo(t, k)
              return (
                <div key={k} className="rev-method">
                  <span className="rev-method__icon" aria-hidden="true">{v.icon}</span>
                  <div>
                    <div className="rev-method__label">{v.label}</div>
                    <div className="u-text2-xs">{v.desc}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* ── Modal nuevo contrato ASC 606 ── */}
      {showCreateContract && (
        <Modal open title={t('revenue.nuevo_contrato_asc_606')} onClose={() => setShowCreateContract(false)} width={540}>
          <div className="u-stack-14">
            <Select label={t('revenue_page.proyecto')} placeholder={false} id={`${idCampo}-4`} value={contractForm.project_id} onChange={e=>setContractForm(f=>({...f,project_id:e.target.value}))}>
                <option value="">{t('revenue_page.seleccionar_proyecto')}</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
              </Select>
            <Input label={t('revenue.nombre_del_contrato')} id={`${idCampo}-5`} value={contractForm.name} onChange={e=>setContractForm(f=>({...f,name:e.target.value}))} placeholder={t('revenue_page.nombre_contrato_ph')} />
            <Select label={t('revenue.metodo_de_reconocimiento')} placeholder={false} id={`${idCampo}-6`} value={contractForm.method} onChange={e=>setContractForm(f=>({...f,method:e.target.value}))}>
                {ASC_METHODS.map(k => { const v = metodo(t, k); return <option key={k} value={k}>{v.label} — {v.desc}</option> })}
              </Select>
            <div className="u-grid2-12">
              <Input label={t('revenue.valor_del_contrato_2')} id={`${idCampo}-7`} type="number" value={contractForm.contract_value} onChange={e=>setContractForm(f=>({...f,contract_value:e.target.value}))} placeholder="50000" />
              <Select label={t('revenue_page.moneda')} placeholder={false} id={`${idCampo}-8`} value={contractForm.currency} onChange={e=>setContractForm(f=>({...f,currency:e.target.value}))}>
                  {monedasDeLaEmpresa.map(c => <option key={c} value={c}>{c}</option>)}
                </Select>
            </div>
            <div className="u-grid2-12">
              <DateInput label={t('revenue_page.fecha_inicio')} id={`${idCampo}-9`} value={contractForm.start_date} onChange={e=>setContractForm(f=>({...f,start_date:e.target.value}))} />
              <DateInput label={t('revenue_page.fecha_fin')} id={`${idCampo}-10`} value={contractForm.end_date} onChange={e=>setContractForm(f=>({...f,end_date:e.target.value}))} />
            </div>
            {contractForm.method === 'straight_line' && (
              <Input label={t('revenue.duracion_meses_alternativa_a_fecha_fin')} id={`${idCampo}-11`} type="number" value={contractForm.duration_months} onChange={e=>setContractForm(f=>({...f,duration_months:e.target.value}))} placeholder="12" />
            )}
            <Textarea label={t('revenue_page.notas')} id={`${idCampo}-12`} value={contractForm.notes} onChange={e=>setContractForm(f=>({...f,notes:e.target.value}))} rows={2} />
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreateContract(false)}>{t('revenue_page.cancelar')}</Button>
              <Button
                onClick={() => createContract({
                  ...contractForm,
                  contract_value: parseFloat(contractForm.contract_value) || 0,
                  duration_months: contractForm.duration_months ? parseInt(contractForm.duration_months) : null,
                })}
                disabled={creatingContract || !contractForm.project_id || !contractForm.name}
              >
                {creatingContract ? t('revenue_page.creando') : t('revenue_page.crear_contrato')}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Modal cerrar período ── */}
      {showCloseModal && (
        <Modal open title={t('revenue.cerrar_periodo_contable')} onClose={() => setShowCloseModal(false)} width={420}>
          <div className="u-stack-14">
            <div className="rev-notice" role="note">
              {t('revenue.una_vez_cerrado_no_se_podran_crear')}
            </div>
            <div className="u-grid2-12">
              <Input label={t('revenue.ano')} id={`${idCampo}-13`} type="number" value={closePeriod.year} onChange={e=>setClosePeriod(p=>({...p,year:parseInt(e.target.value)}))} />
              <Select label={t('revenue_page.mes')} placeholder={false} id={`${idCampo}-14`} value={closePeriod.month} onChange={e=>setClosePeriod(p=>({...p,month:parseInt(e.target.value)}))}>
                  {MONTHS.map((m,i) => <option key={i+1} value={i+1}>{i+1} — {m}</option>)}
                </Select>
            </div>
            {closedPeriodKeys.has(`${closePeriod.year}-${closePeriod.month}`) && (
              <div className="rev-notice rev-notice--danger" role="alert">
                {t('revenue.este_periodo_ya_esta_cerrado')}
              </div>
            )}
            <Textarea label={t('revenue_page.notas_opcional')} id={`${idCampo}-15`} value={closePeriod.notes} onChange={e=>setClosePeriod(p=>({...p,notes:e.target.value}))} rows={2} />
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCloseModal(false)}>{t('revenue_page.cancelar')}</Button>
              <Button
                onClick={() => closePeriodMut({ year: closePeriod.year, month: closePeriod.month, notes: closePeriod.notes || null })}
                disabled={closingPeriod || closedPeriodKeys.has(`${closePeriod.year}-${closePeriod.month}`)}
              >
                {closingPeriod ? t('revenue_page.cerrando') : t('revenue_page.cerrar_periodo')}
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
