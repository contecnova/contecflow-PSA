/**
 * ExpensesPage — gestión completa de gastos con flujo de aprobación
 * Vistas: Mis gastos | Pendientes aprobación | Equipo | Resumen por proyecto
 */
import { useState, useId } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, localeActivo, downloadBlob } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, expensesApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState, useSort, SortableTH, SearchInput, FilterSelect } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Receipt } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import { useOrgSettings } from '../hooks/useOrgSettings'
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer
} from 'recharts'
import DetalleDeGasto from '../components/gastos/DetalleDeGasto'
import PoliticasDeGasto from '../components/gastos/PoliticasDeGasto'
import DsBadge from '../components/ui/StatusBadge'
import DateInput from '../components/ui/DateInput'
import { POLL_FREQUENT_MS } from '../constants/timings'

// ── Config ────────────────────────────────────────────────────────────────────
const CATEGORIES: Record<string, { label: string; icon: string; color: string }> = {
  travel:        { label: 'Viajes',          icon: '✈️',  color: 'var(--accent)' },
  accommodation: { label: 'Alojamiento',     icon: '🏨',  color: 'var(--purple)' },
  meals:         { label: 'Dietas',          icon: '🍽️',  color: 'var(--warning)' },
  software:      { label: 'Software',        icon: '💻',  color: 'var(--success)' },
  hardware:      { label: 'Hardware',        icon: '🖥️',  color: 'var(--warning)' },
  training:      { label: 'Formación',       icon: '📚',  color: 'var(--danger)' },
  subcontract:   { label: 'Subcontratación', icon: '🤝',  color: 'var(--purple)' },
  other:         { label: 'Otros',           icon: '📦',  color: 'var(--text-2)' },
}
const STATUSES: Record<string, { label: string; color: string }> = {
  draft:      { label: 'Borrador',    color: 'var(--text-2)' },
  submitted:  { label: 'Enviado',     color: 'var(--warning)' },
  approved:   { label: 'Aprobado',    color: 'var(--success)' },
  rejected:   { label: 'Rechazado',   color: 'var(--danger)' },
  reimbursed: { label: 'Reembolsado', color: 'var(--accent)' },
}

const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
const card: CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUSES[status] || { label: status, color: 'var(--text-2)' }
  return (
    <DsBadge color={cfg.color} caps={false}>{cfg.label}</DsBadge>
  )
}

function CatBadge({ cat }: { cat: string }) {
  const cfg = CATEGORIES[cat] || { label: cat, icon: '📦', color: 'var(--text-2)' }
  return (
    <DsBadge color={cfg.color} caps={false}>{cfg.icon} {cfg.label}</DsBadge>
  )
}

function fmt(amount: unknown, currency?: string) {
  const v = Number(amount)
  if (!currency) return `${v.toLocaleString(localeActivo(), { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  return `${v.toLocaleString(localeActivo(), { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`
}

// ── Expense row ───────────────────────────────────────────────────────────────
type Expense = {
  [k: string]: unknown
  id: string
  code?: string
  category?: string
  description?: string
  amount?: unknown
  currency?: string
  status?: string
  expense_date?: string
  project_id?: string
  project_name?: string
  user_name?: string
  notes?: string
  receipt_url?: string
  km?: number | null
  policy_flags?: { mensaje: string }[]
  is_billable?: boolean
  submitted_at?: string
  reviewed_by_name?: string
  rejection_reason?: string
  reimbursed_at?: string
  requester_name?: string
}

function ExpenseRow({ expense, onAction, isManager }: { expense: Expense; onAction?: (exp: Expense) => ReactNode; isManager?: boolean }) {
  const t = useAppT()
  const [detalle, setDetalle] = useState(false)
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '80px 110px 1fr 120px 110px 130px auto', minWidth: 820, gap: 12, padding: '12px 18px', borderBottom: '1px solid var(--surface-4)', alignItems: 'center' }}>
      <span className="u-text3-mono-xs">{expense.code}</span>
      <CatBadge cat={expense.category || ''} />
      <div>
        <button type="button" onClick={() => setDetalle(true)} title={t('gas.abrir_detalle')}
          style={{ fontSize: "var(--text-base)", fontWeight: 600, background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--text-1)', textAlign: 'left', fontFamily: 'inherit' }}>
          {expense.description}
        </button>
        {(expense.policy_flags ?? []).length > 0 && <span style={{ marginLeft: 6, fontSize: 'var(--text-2xs)', color: 'var(--warning)' }}>⚠ {t('gas.excede_politica')}</span>}
        <div className="u-text2-xs-mt2">
          {expense.project_name || 'Sin proyecto'} · {expense.expense_date}
          {isManager && <span style={{ marginLeft: 8 }}>· {expense.user_name}</span>}
        </div>
        {expense.receipt_url && (
          <a href={expense.receipt_url} target="_blank" rel="noopener noreferrer"
            onClick={ev => ev.stopPropagation()}
            style={{ fontSize: "var(--text-xs)", color: 'var(--accent)', display: 'inline-flex', alignItems: 'center', gap: 3, marginTop: 3 }}>
            🔗 Justificante
          </a>
        )}
      </div>
      <span style={{ fontSize: "var(--text-md)", fontWeight: 700, textAlign: 'right', color: expense.is_billable ? 'var(--success)' : 'var(--text-1)' }}>
        {fmt(expense.amount, expense.currency)}
        {expense.is_billable && <span style={{ fontSize: "var(--text-2xs)", color: 'rgba(52,211,153,0.50)', display: 'block' }}>facturable</span>}
      </span>
      <StatusBadge status={expense.status || ''} />
      <div className="u-text3-xs">
        {expense.status === 'submitted' && expense.submitted_at && `Enviado ${expense.submitted_at.slice(0, 10)}`}
        {expense.status === 'approved' && expense.reviewed_by_name && `✓ ${expense.reviewed_by_name}`}
        {expense.status === 'rejected' && <span className="u-danger">{expense.rejection_reason}</span>}
        {expense.status === 'reimbursed' && expense.reimbursed_at && `💰 ${expense.reimbursed_at}`}
      </div>
      <div className="u-row-6">
        {onAction && onAction(expense)}
      </div>
      {detalle && <DetalleDeGasto gasto={{ ...expense, amount: expense.amount as number }} editable={expense.status === 'draft' || !!isManager} onClose={() => setDetalle(false)} />}
    </div>
  )
}

// ── Create/Edit expense modal ─────────────────────────────────────────────────
function ExpenseModal({ expense, onClose }: { expense?: Expense; onClose: () => void }) {
  const idCampo = useId()
  const traducir = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { invalidate: _invalidate } = useInvalidate()
  const { currency: defaultCurrency, currencies: monedasDeLaEmpresa } = useOrgSettings()
  const isEdit = !!expense
  const [ocrLoading, setOcrLoading] = useState(false)
  const [form, setForm] = useState<{
    project_id: string; category: string; description: string; amount: string | number;
    currency: string; expense_date: string; is_billable: boolean; notes: string; km: string
  }>({
    project_id:  expense?.project_id  || '',
    category:    expense?.category    || 'travel',
    description: expense?.description || '',
    amount:      (expense?.amount as string | number) || '',
    currency:    expense?.currency    || defaultCurrency,
    expense_date: expense?.expense_date || new Date().toISOString().slice(0, 10),
    is_billable: expense?.is_billable ?? true,
    notes:       expense?.notes       || '',
    km:          expense?.km ? String(expense.km) : '',
  })
  const set = (k: string) => (e: { target: { value: string } }) => setForm(f => ({ ...f, [k]: e.target.value }))

  const { data: projRaw = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data) })
  const projects: Array<{ id?: string; code?: string; name?: string }> = Array.isArray(projRaw) ? projRaw : []

  const { mutate, isPending } = useMutation({
    mutationFn: (d: Record<string, unknown>) => isEdit ? expensesApi.updateMy(expense!.id, d) : expensesApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['expenses-my'] }); qc.invalidateQueries({ queryKey: ['expenses-pending'] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <Modal open title={isEdit ? 'Editar gasto' : 'Nuevo gasto'} onClose={onClose} width={580}>
      {/* OCR receipt scan button */}
      {!isEdit && (
        <div style={{ marginBottom: 16, padding: '12px 14px', background: 'var(--accent-muted)', border: '1px dashed var(--accent-glow)', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ fontSize: "var(--text-xl)" }}>📷</span>
          <div style={{ flex: '1 1 180px', minWidth: 0 }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 2 }}>{traducir('expenses.escanear_recibo_con_ia')}</div>
            <div className="u-text2-xs">{traducir('expenses.sube_una_foto_o_pdf_y_el')}</div>
          </div>
          <label style={{ cursor: 'pointer' }}>
            <input type="file" accept="image/*,.pdf" style={{ display: 'none' }} onChange={async e => {
              const file = e.target.files?.[0]
              if (!file) return
              setOcrLoading(true)
              try {
                const fd = new FormData(); fd.append('file', file)
                const res = await expensesApi.ocr(fd)
                const ex = res.data.extracted
                setForm(f => ({
                  ...f,
                  amount:       ex.amount  ?? f.amount,
                  currency:     ex.currency ?? f.currency,
                  description:  ex.description || (ex.merchant ? `Gasto en ${ex.merchant}` : f.description),
                  expense_date: ex.date    ?? f.expense_date,
                  category:     ex.category ?? f.category,
                }))
                toast.success('¡Recibo escaneado! Revisa y completa los campos.')
              } catch (err) {
                toast.error(extractErr(err, 'Error al escanear recibo'))
              } finally {
                setOcrLoading(false)
                e.target.value = ''
              }
            }} />
            <Button variant="secondary" disabled={ocrLoading} style={{ pointerEvents: 'none' }}>
              {ocrLoading ? '⏳ Analizando...' : '📎 Subir recibo'}
            </Button>
          </label>
        </div>
      )}
      <div className="u-grid2-14">
        <div className="u-col-full">
          <label style={ls}>{traducir('expenses.descripcion')}</label>
          <input value={form.description} onChange={set('description')} style={fs} placeholder={traducir('expenses.descripcion_del_gasto')} aria-label={traducir('expenses.descripcion_del_gasto')} />
        </div>
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{traducir('expenses.category')}</label>
          <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.category} onChange={set('category')} style={fs}>
            {Object.entries(CATEGORIES).map(([v, c]) => <option key={v} value={v}>{c.icon} {c.label}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>Proyecto</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.project_id} onChange={set('project_id')} style={fs}>
            <option value="">{traducir('expenses.sin_proyecto')}</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Importe *</label>
          <input type="number" step="0.01" value={form.km ? '' : form.amount} disabled={!!form.km} onChange={set('amount')} style={fs}
            placeholder={form.km ? traducir('gas.importe_por_km') : 'Importe'} aria-label="Importe" />
        </div>
        <div>
          <label style={ls}>{traducir('gas.km')}</label>
          <input type="number" step="0.1" min={0} value={form.km} onChange={set('km')} style={fs} placeholder={traducir('gas.km_ayuda')} aria-label={traducir('gas.km')} />
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>Moneda</label>
          <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.currency} onChange={set('currency')} style={fs}>
            {monedasDeLaEmpresa.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>{traducir('expenses.fecha_del_gasto')}</label>
          <DateInput id={`${idCampo}-4`} value={form.expense_date} onChange={set('expense_date')} style={fs} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingTop: 24 }}>
          <input type="checkbox" id="billable" checked={form.is_billable} onChange={e => setForm(f => ({ ...f, is_billable: e.target.checked }))} />
          <label htmlFor="billable" style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', cursor: 'pointer' }}>{traducir('expenses.gasto_facturable_al_cliente')}</label>
        </div>
        <div className="u-col-full">
          <label style={ls}>Notas adicionales</label>
          <textarea value={form.notes} onChange={set('notes')} rows={2} style={{ ...fs, resize: 'vertical' }} placeholder="Notas adicionales" aria-label="Notas adicionales" />
        </div>
        <div style={{ gridColumn: '1/-1', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{traducir('gas.justificantes_en_el_detalle')}</div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => { const { km, ...resto } = form; mutate(km ? { ...resto, km: Number(km), amount: Number(resto.amount) || 0 } : resto) }}
            disabled={isPending || !form.description || (!form.amount && !form.km) || !form.expense_date} loading={isPending}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar cambios' : 'Crear gasto'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Review modal ──────────────────────────────────────────────────────────────
function ReviewModal({ expense, onClose }: { expense: Expense; onClose: () => void }) {
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [reason, setReason] = useState('')
  const { mutate, isPending } = useMutation({
    mutationFn: (d: Record<string, unknown>) => expensesApi.review(expense.id, d),
    onSuccess: (r: { data?: { avisos_de_presupuesto?: string[] } }) => {
      // Control presupuestario (BUDGET_CONTROL_POLICY = avisar): se aprueba, y se dice de qué presupuesto se pasa.
      for (const aviso of r?.data?.avisos_de_presupuesto ?? []) toast.warning(aviso, 8000)
      qc.invalidateQueries({ queryKey: ['expenses-pending'] }); qc.invalidateQueries({ queryKey: ['expenses-team'] }); onClose()
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <Modal open title={`Revisar gasto — ${expense.code}`} onClose={onClose} width={480}>
      <div style={{ marginBottom: 16, background: 'var(--surface-3)', borderRadius: 'var(--radius-md)', padding: '14px 16px' }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4 }}>{expense.description}</div>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: "var(--text-base)", color: 'var(--text-2)' }}>
          <span>👤 {expense.user_name}</span>
          <span><CatBadge cat={expense.category || ''} /></span>
          <span style={{ color: 'var(--text-1)', fontWeight: 700 }}>{fmt(expense.amount, expense.currency)}</span>
        </div>
        {expense.notes && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginTop: 8 }}>{expense.notes}</div>}
        {expense.receipt_url && (
          <a href={expense.receipt_url} target="_blank" rel="noopener noreferrer"
            style={{ fontSize: "var(--text-sm)", color: 'var(--accent)', display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 8 }}>
            🔗 Ver justificante / factura adjunta
          </a>
        )}
      </div>
      <div className="u-mb-16">
        <label style={ls}>{traducir('expenses.motivo_de_rechazo_si_aplica')}</label>
        <input value={reason} onChange={e => setReason(e.target.value)} style={fs} placeholder={traducir('expenses.motivo_de_rechazo')} aria-label={traducir('expenses.motivo_de_rechazo')} />
      </div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>Cancelar</Button>
        <button onClick={() => mutate({ approved: false, rejection_reason: reason })} disabled={isPending || !reason}
          style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 8, padding: '9px 18px', color: 'var(--danger)', cursor: 'pointer', fontFamily: 'inherit', fontSize: "var(--text-base)", fontWeight: 600 }}>
          ✗ Rechazar
        </button>
        <button onClick={() => mutate({ approved: true })} disabled={isPending}
          style={{ background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 8, padding: '9px 18px', color: 'var(--success)', cursor: 'pointer', fontFamily: 'inherit', fontSize: "var(--text-base)", fontWeight: 600 }}>
          ✓ Aprobar
        </button>
      </div>
    </Modal>
  )
}

// ── Tab: Mis gastos ───────────────────────────────────────────────────────────
function MyExpenses() {
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<Expense | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')
  const [catFilter, setCatFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const { data: raw = [], isLoading } = useQuery<Expense[]>({
    queryKey: ['expenses-my', statusFilter],
    queryFn: () => expensesApi.my({ status: statusFilter || undefined }).then(r => r.data?.items ?? r.data ?? []),
  })
  const expenses: Expense[] = Array.isArray(raw) ? raw : []
  const filteredExpenses = expenses.filter(e => {
    if (search) {
      const q = search.toLowerCase()
      const haystack = `${e.code || ''} ${e.description || ''} ${e.category || ''}`.toLowerCase()
      if (!haystack.includes(q)) return false
    }
    if (catFilter && e.category !== catFilter) return false
    if (dateFrom && e.expense_date && e.expense_date < dateFrom) return false
    if (dateTo && e.expense_date && e.expense_date > dateTo) return false
    return true
  })
  const { sort: expSort, setSort: setExpSort, sortedData: sortedExpenses } = useSort(filteredExpenses, 'expense_date', 'desc')
  const dateInput = (val: string): CSSProperties => ({ background: val ? 'var(--accent-muted)' : 'var(--surface-2)', border: `1px solid ${val ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 8, padding: '8px 12px', color: val ? 'var(--accent)' : 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit', outline: 'none' })
  const hasFilter = search || statusFilter || catFilter || dateFrom || dateTo

  const { mutate: submit, isPending: saving } = useMutation({
    mutationFn: (id: string) => expensesApi.submitMy(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['expenses-my'] }); qc.invalidateQueries({ queryKey: ['expenses-pending'] }); },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: recall } = useMutation({
    mutationFn: (id: string) => expensesApi.recall(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['expenses-my'] }); qc.invalidateQueries({ queryKey: ['expenses-pending'] }); },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id: string) => expensesApi.deleteMy(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['expenses-my'] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const total = expenses.reduce((s, e) => s + (Number(e.amount) || 0), 0)
  const pending = expenses.filter(e => e.status === 'submitted').length

  return (
    <div>
      <div style={{ display: 'flex', gap: 14, marginBottom: 20, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {[
            { label: 'Total', value: fmt(total), color: 'var(--text-1)' },
            { label: 'Pendientes', value: pending, color: pending > 0 ? 'var(--warning)' : 'var(--text-2)' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ ...card, padding: '10px 16px', minWidth: 120 }}>
              <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 800, color }}>{value}</div>
              <div className="u-text2-xs">{label}</div>
            </div>
          ))}
        </div>
        <Button onClick={() => setShowCreate(true)} style={{ marginLeft: 'auto' }}>{traducir('expenses.nuevo_gasto')}</Button>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 14 }}>
        <SearchInput value={search} onChange={setSearch} placeholder={traducir('expenses.buscar_codigo_o_descripcion')} style={{ minWidth: 220, flex: '1 1 220px', maxWidth: 320 }} />
        <FilterSelect value={statusFilter} onChange={setStatusFilter} placeholder="Estado" options={Object.entries(STATUSES).map(([v, c]) => ({ value: v, label: c.label }))} />
        <FilterSelect value={catFilter} onChange={setCatFilter} placeholder="Tipo" options={Object.entries(CATEGORIES).map(([v, c]) => ({ value: v, label: `${c.icon} ${c.label}` }))} />
        <DateInput aria-label="Desde" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={dateInput(dateFrom)} />
        <span className="u-text3">—</span>
        <DateInput aria-label="Hasta" value={dateTo} onChange={e => setDateTo(e.target.value)} style={dateInput(dateTo)} />
        {hasFilter && (
          <button onClick={() => { setSearch(''); setStatusFilter(''); setCatFilter(''); setDateFrom(''); setDateTo('') }}
            style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-2)', fontSize: 'var(--text-sm)', cursor: 'pointer', fontFamily: 'inherit' }}>Limpiar</button>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{sortedExpenses.length} / {expenses.length}</span>
      </div>

      {isLoading ? <Spinner /> : expenses.length === 0 ? (
        <EmptyState icon="💸" title={traducir('expenses.sin_gastos')} description="Crea tu primer gasto para empezar a registrarlos." />
      ) : sortedExpenses.length === 0 ? (
        <EmptyState icon="🔍" title={traducir('expenses.sin_resultados')} description="Ningún gasto coincide con los filtros aplicados." />
      ) : (
        <div style={{ ...card, overflowX: 'auto' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '80px 110px 1fr 120px 110px 130px auto', minWidth: 820, gap: 12, padding: '10px 18px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
            <SortableTH col="code" sort={expSort} onSort={setExpSort}>#</SortableTH>
            <SortableTH col="category" sort={expSort} onSort={setExpSort}>Tipo</SortableTH>
            <SortableTH col="description" sort={expSort} onSort={setExpSort}>{traducir('expenses.descripcion_2')}</SortableTH>
            <SortableTH col="amount" sort={expSort} onSort={setExpSort}>Importe</SortableTH>
            <SortableTH col="status" sort={expSort} onSort={setExpSort}>Estado</SortableTH>
            <SortableTH col="expense_date" sort={expSort} onSort={setExpSort}>Info</SortableTH>
            <span></span>
          </div>
          {sortedExpenses.map(e => (
            <ExpenseRow key={e.id} expense={e} isManager={false} onAction={(exp) => (
              <div style={{ display: 'flex', gap: 5 }}>
                {exp.status === 'draft' && <>
                  <button onClick={() => setEditing(exp)} title="Editar gasto" aria-label="Editar gasto"
                    style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>✏</button>
                  <button onClick={() => submit(exp.id)} title="Enviar gasto" aria-label="Enviar gasto"
                    style={{ background: 'var(--warning-bg)', border: '1px solid var(--warning-border)', borderRadius: 'var(--radius-sm)', padding: '3px 8px', color: 'var(--warning)', cursor: 'pointer', fontSize: "var(--text-sm)" }} disabled={saving}>↑ Enviar</button>
                  <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar este gasto?', onConfirm: () => del(exp.id), danger: true }) }} title="Eliminar gasto" aria-label="Eliminar gasto"
                    style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>🗑</button>
                </>}
                {exp.status === 'submitted' && (
                  <button onClick={() => recall(exp.id)} title="Retirar gasto" aria-label="Retirar gasto"
                    style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>↩ Retirar</button>
                )}
                {exp.status === 'rejected' && (
                  <button onClick={() => setEditing(exp)} title="Editar gasto rechazado" aria-label="Editar gasto rechazado"
                    style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>✏ Editar</button>
                )}
              </div>
            )} />
          ))}
        </div>
      )}
      {showCreate && <ExpenseModal onClose={() => setShowCreate(false)} />}
      {editing && <ExpenseModal expense={editing} onClose={() => setEditing(null)} />}
    </div>
  )
}

// ── Tab: Pendientes aprobación ────────────────────────────────────────────────
function PendingApproval() {
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [reviewing, setReviewing] = useState<Expense | null>(null)

  const { data: raw = [], isLoading } = useQuery<Expense[]>({
    queryKey: ['expenses-pending'],
    queryFn: () => expensesApi.pending().then(r => r.data),
    refetchInterval: POLL_FREQUENT_MS,
  })
  const expenses: Expense[] = Array.isArray(raw) ? raw : []
  const [pendSearch, setPendSearch] = useState('')
  const [pendCat, setPendCat] = useState('')
  const [pendFrom, setPendFrom] = useState('')
  const [pendTo, setPendTo] = useState('')
  const filteredPending = expenses.filter(e => {
    if (pendSearch) {
      const q = pendSearch.toLowerCase()
      const haystack = `${e.code || ''} ${e.description || ''} ${e.user_name || ''} ${e.requester_name || ''}`.toLowerCase()
      if (!haystack.includes(q)) return false
    }
    if (pendCat && e.category !== pendCat) return false
    if (pendFrom && e.expense_date && e.expense_date < pendFrom) return false
    if (pendTo && e.expense_date && e.expense_date > pendTo) return false
    return true
  })
  const { sort: pendSort, setSort: setPendSort, sortedData: sortedPending } = useSort(filteredPending, 'expense_date', 'desc')
  const dateInput = (val: string): CSSProperties => ({ background: val ? 'var(--accent-muted)' : 'var(--surface-2)', border: `1px solid ${val ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 8, padding: '8px 12px', color: val ? 'var(--accent)' : 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit', outline: 'none' })
  const hasFilter = pendSearch || pendCat || pendFrom || pendTo

  const { mutate: _reimburse } = useMutation({
    mutationFn: (id: string) => expensesApi.reimburse(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['expenses-pending'] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div>
      <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginBottom: 16 }}>
        {expenses.length > 0 ? `${expenses.length} gasto(s) pendientes de revisión · ${fmt(expenses.reduce((s, e) => s + (Number(e.amount) || 0), 0))} total` : 'No hay gastos pendientes'}
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 14 }}>
        <SearchInput value={pendSearch} onChange={setPendSearch} placeholder={traducir('expenses.buscar_codigo_descripcion_o_solicitante')} style={{ minWidth: 240, flex: '1 1 240px', maxWidth: 360 }} />
        <FilterSelect value={pendCat} onChange={setPendCat} placeholder="Tipo" options={Object.entries(CATEGORIES).map(([v, c]) => ({ value: v, label: `${c.icon} ${c.label}` }))} />
        <DateInput aria-label="Desde" value={pendFrom} onChange={e => setPendFrom(e.target.value)} style={dateInput(pendFrom)} />
        <span className="u-text3">—</span>
        <DateInput aria-label="Hasta" value={pendTo} onChange={e => setPendTo(e.target.value)} style={dateInput(pendTo)} />
        {hasFilter && (
          <button onClick={() => { setPendSearch(''); setPendCat(''); setPendFrom(''); setPendTo('') }}
            style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-2)', fontSize: 'var(--text-sm)', cursor: 'pointer', fontFamily: 'inherit' }}>Limpiar</button>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{sortedPending.length} / {expenses.length}</span>
      </div>
      {isLoading ? <Spinner /> : expenses.length === 0 ? (
        <EmptyState icon="✅" title={traducir('expenses.sin_pendientes')} description="No hay gastos pendientes de revisión." />
      ) : sortedPending.length === 0 ? (
        <EmptyState icon="🔍" title={traducir('expenses.sin_resultados')} description="Ningún gasto pendiente coincide con los filtros aplicados." />
      ) : (
        <div style={{ ...card, overflowX: 'auto' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '80px 110px 1fr 120px 110px 130px auto', minWidth: 820, gap: 12, padding: '10px 18px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
            <SortableTH col="code" sort={pendSort} onSort={setPendSort}>#</SortableTH>
            <SortableTH col="category" sort={pendSort} onSort={setPendSort}>Tipo</SortableTH>
            <SortableTH col="description" sort={pendSort} onSort={setPendSort}>{traducir('expenses.descripcion_2')}</SortableTH>
            <SortableTH col="amount" sort={pendSort} onSort={setPendSort}>Importe</SortableTH>
            <SortableTH col="status" sort={pendSort} onSort={setPendSort}>Estado</SortableTH>
            <SortableTH col="expense_date" sort={pendSort} onSort={setPendSort}>Solicitante</SortableTH>
            <span></span>
          </div>
          {sortedPending.map(e => (
            <ExpenseRow key={e.id} expense={e} isManager onAction={(exp) => (
              <div style={{ display: 'flex', gap: 5 }}>
                <button onClick={() => setReviewing(exp)}
                  style={{ background: 'var(--warning-bg)', border: '1px solid var(--warning-border)', borderRadius: 'var(--radius-sm)', padding: '3px 10px', color: 'var(--warning)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>
                  Revisar
                </button>
              </div>
            )} />
          ))}
        </div>
      )}
      {reviewing && <ReviewModal expense={reviewing} onClose={() => setReviewing(null)} />}
    </div>
  )
}

// ── Tab: Equipo (resumen + todos) ─────────────────────────────────────────────
function TeamExpenses() {
  const traducir = useAppT()
  const toast = useToast()
  const [projectFilter, setProjectFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [_period, _setPeriod] = useState('')

  const { data: projRaw = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data) })
  const projects: Array<{ id?: string; code?: string; name?: string }> = Array.isArray(projRaw) ? projRaw : []

  type TeamData = { expenses?: Expense[]; total?: number; billable_total?: number; by_category?: Record<string, number> }
  const { data: raw, isLoading } = useQuery<TeamData>({
    queryKey: ['expenses-team', projectFilter, statusFilter],
    queryFn: () => expensesApi.team({ project_id: projectFilter || undefined, status: statusFilter || undefined }).then(r => r.data),
  })

  const expenses: Expense[] = raw?.expenses || []
  const { sort: teamSort, setSort: setTeamSort, sortedData: sortedTeam } = useSort(expenses, 'expense_date', 'desc')
  const total = raw?.total || 0
  const billable = raw?.billable_total || 0
  const byCat: Record<string, number> = raw?.by_category || {}

  const catChartData = Object.entries(byCat).map(([k, v]) => ({
    name: CATEGORIES[k]?.label || k,
    value: v,
    color: CATEGORIES[k]?.color || 'var(--text-2)',
  }))

  const qcTeam = useQueryClient()
  const { mutate: reimburse } = useMutation({
    mutationFn: (id: string) => expensesApi.reimburse(id),
    onSuccess: () => qcTeam.invalidateQueries({ queryKey: ['expenses-team'] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
        <select value={projectFilter} onChange={e => setProjectFilter(e.target.value)} style={{ ...fs, width: 'auto', maxWidth: '100%' }}>
          <option value="">{traducir('expenses.todos_los_proyectos')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
        </select>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ ...fs, width: 'auto' }}>
          <option value="">{traducir('expenses.todos_los_estados')}</option>
          {Object.entries(STATUSES).map(([v, c]) => <option key={v} value={v}>{c.label}</option>)}
        </select>
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(150px, 100%), 1fr))', gap: 14, marginBottom: 24 }}>
        {[
          { label: 'Total gastos', value: fmt(total), color: 'var(--text-1)', icon: '💸' },
          { label: 'Facturable', value: fmt(billable), color: 'var(--success)', icon: '📄' },
          { label: 'No facturable', value: fmt(total - billable), color: 'var(--text-2)', icon: '🔒' },
          { label: 'Nº gastos', value: expenses.length, color: 'var(--accent)', icon: '🧾' },
        ].map(({ label, value, color, icon }) => (
          <div key={label} style={{ ...card, padding: '14px 18px' }}>
            <div style={{ fontSize: "var(--text-xl)", marginBottom: 6 }}>{icon}</div>
            <div style={{ fontSize: "var(--text-xl)", fontWeight: 800, color }}>{value}</div>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Chart by category */}
      {catChartData.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(320px, 100%), 1fr))', gap: 20, marginBottom: 24 }}>
          <div style={{ ...card, padding: '16px 20px' }}>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>{traducir('expenses.por_categoria')}</div>
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={catChartData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} paddingAngle={2}>
                  {catChartData.map((e, i) => <Cell key={i} fill={e.color} />)}
                </Pie>
                <Tooltip formatter={v => fmt(v)} contentStyle={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, fontSize: "var(--text-xs)" }} />
              </PieChart>
            </ResponsiveContainer>
            {catChartData.map(d => (
              <div key={d.name} style={{ display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-sm)", padding: '2px 0' }}>
                <span style={{ color: d.color }}>● {d.name}</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>{fmt(d.value)}</span>
              </div>
            ))}
          </div>
          <div style={{ ...card, padding: '16px 20px' }}>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>{traducir('expenses.distribucion')}</div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={catChartData} margin={{ top: 0, right: 0, left: -10, bottom: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="name" tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} angle={-30} textAnchor="end" />
                <YAxis tick={{ fontSize: "var(--text-2xs)", fill: 'var(--text-2)' }} />
                <Tooltip formatter={v => fmt(v)} contentStyle={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, fontSize: "var(--text-xs)" }} />
                <Bar dataKey="value" radius={[3, 3, 0, 0]}>
                  {catChartData.map((e, i) => <Cell key={i} fill={e.color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Table */}
      {isLoading ? <Spinner /> : expenses.length === 0 ? (
        <EmptyState icon="💸" title={traducir('expenses.sin_gastos_del_equipo')} description="No hay gastos para los filtros seleccionados." />
      ) : (
        <div style={{ ...card, overflowX: 'auto' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '80px 110px 1fr 120px 110px 130px auto', minWidth: 820, gap: 12, padding: '10px 18px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
            <SortableTH col="code" sort={teamSort} onSort={setTeamSort}>#</SortableTH>
            <SortableTH col="category" sort={teamSort} onSort={setTeamSort}>Tipo</SortableTH>
            <SortableTH col="description" sort={teamSort} onSort={setTeamSort}>{traducir('expenses.descripcion_2')}</SortableTH>
            <SortableTH col="amount" sort={teamSort} onSort={setTeamSort}>Importe</SortableTH>
            <SortableTH col="status" sort={teamSort} onSort={setTeamSort}>Estado</SortableTH>
            <SortableTH col="expense_date" sort={teamSort} onSort={setTeamSort}>{traducir('expenses.revision')}</SortableTH>
            <span></span>
          </div>
          {sortedTeam.map(e => (
            <ExpenseRow key={e.id} expense={e} isManager onAction={(exp) => (
              <div>
                {exp.status === 'approved' && (
                  <button onClick={() => reimburse(exp.id)}
                    style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border-strong)', borderRadius: 'var(--radius-sm)', padding: '3px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>
                    💰 Reembolsar
                  </button>
                )}
              </div>
            )} />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ExpensesPage(): JSX.Element {
  const t = useAppT()
  const { hasRole } = useAuth()
  const isManager = hasRole('admin', 'pm', 'hr')
  const toast = useToast()
  const [tab, setTab] = useState('my')

  const TABS = [
    { id: 'my', label: 'Mis gastos' },
    ...(isManager ? [
      { id: 'pending', label: '⏳ Pendientes aprobación' },
      { id: 'team', label: 'Equipo' },
    ] : []),
    ...(hasRole('admin') ? [{ id: 'politicas', label: t('gas.tab_politicas') }] : []),
  ]

  return (
    <PageShell>
      <PageHeader
        icon={<Receipt size={18} />}
        title={t('expenses.title')}
        subtitle={t('expenses.subtitle')}
        showListExport={false}
        actions={
          <button
            onClick={async () => {
              // Por el cliente (refresco de sesión y errores); antes abría la URL en otra pestaña.
              try {
                const r = await expensesApi.exportExcel()
                const nombre = /filename="?([^";]+)"?/.exec(String(r.headers?.['content-disposition'] ?? ''))?.[1] || 'gastos.xlsx'
                downloadBlob(r.data as Blob, nombre)
              } catch (e) {
                toast.error(extractErr(e, 'No se pudo exportar'))
              }
            }}
            style={{ display: 'flex', alignItems: 'center', gap: 6,
              background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
              borderRadius: 8, padding: '8px 14px', color: 'var(--text-1)',
              cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', fontWeight: 600 }}>
            📊 Exportar Excel
          </button>
        }
      />
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 , borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ padding: '5px 14px', borderRadius: 'var(--radius-sm)', border: `1px solid ${tab === t.id ? 'var(--accent)' : 'var(--surface-4)'}`, background: tab === t.id ? 'var(--accent-muted)' : 'transparent', color: tab === t.id ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'my'      && <MyExpenses />}
      {tab === 'pending' && <PendingApproval />}
      {tab === 'team'    && <TeamExpenses />}
      {tab === 'politicas' && <PoliticasDeGasto categorias={Object.entries(CATEGORIES).map(([id, c]) => ({ id, label: c.label }))} />}
    </PageShell>
  )
}
