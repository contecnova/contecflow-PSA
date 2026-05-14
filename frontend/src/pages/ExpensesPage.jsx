/**
 * ExpensesPage — gestión completa de gastos con flujo de aprobación
 * Vistas: Mis gastos | Pendientes aprobación | Equipo | Resumen por proyecto
 */
import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
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

// ── Config ────────────────────────────────────────────────────────────────────
const CATEGORIES = {
  travel:        { label: 'Viajes',          icon: '✈️',  color: 'var(--accent)' },
  accommodation: { label: 'Alojamiento',     icon: '🏨',  color: 'var(--purple)' },
  meals:         { label: 'Dietas',          icon: '🍽️',  color: 'var(--warning)' },
  software:      { label: 'Software',        icon: '💻',  color: 'var(--success)' },
  hardware:      { label: 'Hardware',        icon: '🖥️',  color: 'var(--warning)' },
  training:      { label: 'Formación',       icon: '📚',  color: 'var(--danger)' },
  subcontract:   { label: 'Subcontratación', icon: '🤝',  color: 'var(--purple)' },
  other:         { label: 'Otros',           icon: '📦',  color: 'var(--text-2)' },
}
const STATUSES = {
  draft:      { label: 'Borrador',    color: 'var(--text-2)' },
  submitted:  { label: 'Enviado',     color: 'var(--warning)' },
  approved:   { label: 'Aprobado',    color: 'var(--success)' },
  rejected:   { label: 'Rechazado',   color: 'var(--danger)' },
  reimbursed: { label: 'Reembolsado', color: 'var(--accent)' },
}

const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
const card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }

function StatusBadge({ status }) {
  const cfg = STATUSES[status] || { label: status, color: 'var(--text-2)' }
  return (
    <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: cfg.color + '20', color: cfg.color, border: `1px solid ${cfg.color}40`, whiteSpace: 'nowrap' }}>
      {cfg.label}
    </span>
  )
}

function CatBadge({ cat }) {
  const cfg = CATEGORIES[cat] || { label: cat, icon: '📦', color: 'var(--text-2)' }
  return (
    <span style={{ fontSize: "var(--text-xs)", padding: '2px 7px', borderRadius: 6, background: cfg.color + '15', color: cfg.color }}>
      {cfg.icon} {cfg.label}
    </span>
  )
}

function fmt(amount, currency) {
  const v = Number(amount)
  if (!currency) return `${v.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  return `${v.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`
}

// ── Expense row ───────────────────────────────────────────────────────────────
function ExpenseRow({ expense, onAction, isManager }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '80px 110px 1fr 120px 110px 130px auto', gap: 12, padding: '12px 18px', borderBottom: '1px solid var(--surface-4)', alignItems: 'center' }}>
      <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>{expense.code}</span>
      <CatBadge cat={expense.category} />
      <div>
        <div style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>{expense.description}</div>
        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2 }}>
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
      <StatusBadge status={expense.status} />
      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
        {expense.status === 'submitted' && expense.submitted_at && `Enviado ${expense.submitted_at.slice(0, 10)}`}
        {expense.status === 'approved' && expense.reviewed_by_name && `✓ ${expense.reviewed_by_name}`}
        {expense.status === 'rejected' && <span style={{ color: 'var(--danger)' }}>{expense.rejection_reason}</span>}
        {expense.status === 'reimbursed' && expense.reimbursed_at && `💰 ${expense.reimbursed_at}`}
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        {onAction && onAction(expense)}
      </div>
    </div>
  )
}

// ── Create/Edit expense modal ─────────────────────────────────────────────────
function ExpenseModal({ expense, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { _invalidate } = useInvalidate()
  const { currency: defaultCurrency } = useOrgSettings()
  const isEdit = !!expense
  const [ocrLoading, setOcrLoading] = useState(false)
  const [form, setForm] = useState({
    project_id:  expense?.project_id  || '',
    category:    expense?.category    || 'travel',
    description: expense?.description || '',
    amount:      expense?.amount      || '',
    currency:    expense?.currency    || defaultCurrency,
    expense_date: expense?.expense_date || new Date().toISOString().slice(0, 10),
    is_billable: expense?.is_billable ?? true,
    notes:       expense?.notes       || '',
    receipt_url: expense?.receipt_url || '',
  })
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  const { data: projRaw = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data) })
  const projects = Array.isArray(projRaw) ? projRaw : []

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit ? expensesApi.updateMy(expense.id, d) : expensesApi.create(d),
    onSuccess: () => { qc.invalidateQueries(['expenses-my']); qc.invalidateQueries(['expenses-pending']); onClose() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <Modal open title={isEdit ? 'Editar gasto' : 'Nuevo gasto'} onClose={onClose} width={580}>
      {/* OCR receipt scan button */}
      {!isEdit && (
        <div style={{ marginBottom: 16, padding: '12px 14px', background: 'var(--accent-muted)', border: '1px dashed var(--accent-glow)', borderRadius: 10, display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: "var(--text-xl)" }}>📷</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 2 }}>Escanear recibo con IA</div>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>Sube una foto o PDF y el sistema rellenará los campos automáticamente</div>
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
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Descripción *</label>
          <input value={form.description} onChange={set('description')} style={fs} placeholder="Descripción del gasto" aria-label="Descripción del gasto" />
        </div>
        <div>
          <label style={ls}>Categoría</label>
          <select value={form.category} onChange={set('category')} style={fs}>
            {Object.entries(CATEGORIES).map(([v, c]) => <option key={v} value={v}>{c.icon} {c.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Proyecto</label>
          <select value={form.project_id} onChange={set('project_id')} style={fs}>
            <option value="">Sin proyecto</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Importe *</label>
          <input type="number" step="0.01" value={form.amount} onChange={set('amount')} style={fs} placeholder="Importe" aria-label="Importe" />
        </div>
        <div>
          <label style={ls}>Moneda</label>
          <select value={form.currency} onChange={set('currency')} style={fs}>
            {['EUR','USD','GBP','PLN','CHF'].map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Fecha del gasto *</label>
          <input type="date" value={form.expense_date} onChange={set('expense_date')} style={fs} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingTop: 24 }}>
          <input type="checkbox" id="billable" checked={form.is_billable} onChange={e => setForm(f => ({ ...f, is_billable: e.target.checked }))} />
          <label htmlFor="billable" style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', cursor: 'pointer' }}>Gasto facturable al cliente</label>
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Notas adicionales</label>
          <textarea value={form.notes} onChange={set('notes')} rows={2} style={{ ...fs, resize: 'vertical' }} placeholder="Notas adicionales" aria-label="Notas adicionales" />
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>URL del justificante / factura (opcional)</label>
          <input
            value={form.receipt_url}
            onChange={set('receipt_url')}
            style={fs}
            placeholder="URL del justificante"
            aria-label="URL del justificante"
          />
          {form.receipt_url && (
            <a href={form.receipt_url} target="_blank" rel="noopener noreferrer"
              style={{ fontSize: "var(--text-xs)", color: 'var(--accent)', marginTop: 4, display: 'inline-block' }}>
              🔗 Ver justificante
            </a>
          )}
        </div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.description || !form.amount || !form.expense_date} loading={isPending}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar cambios' : 'Crear gasto'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Review modal ──────────────────────────────────────────────────────────────
function ReviewModal({ expense, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [reason, setReason] = useState('')
  const { mutate, isPending } = useMutation({
    mutationFn: d => expensesApi.review(expense.id, d),
    onSuccess: () => { qc.invalidateQueries(['expenses-pending']); qc.invalidateQueries(['expenses-team']); onClose() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <Modal open title={`Revisar gasto — ${expense.code}`} onClose={onClose} width={480}>
      <div style={{ marginBottom: 16, background: 'var(--surface-3)', borderRadius: 10, padding: '14px 16px' }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4 }}>{expense.description}</div>
        <div style={{ display: 'flex', gap: 16, fontSize: "var(--text-base)", color: 'var(--text-2)' }}>
          <span>👤 {expense.user_name}</span>
          <span><CatBadge cat={expense.category} /></span>
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
      <div style={{ marginBottom: 16 }}>
        <label style={ls}>Motivo de rechazo (si aplica)</label>
        <input value={reason} onChange={e => setReason(e.target.value)} style={fs} placeholder="Motivo de rechazo" aria-label="Motivo de rechazo" />
      </div>
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
        <Button variant="secondary" onClick={onClose}>Cancelar</Button>
        <button onClick={() => mutate({ approved: false, rejection_reason: reason })} disabled={isPending || !reason}
          style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 8, padding: '9px 18px', color: 'var(--danger)', cursor: 'pointer', fontFamily: 'inherit', fontSize: "var(--text-base)", fontWeight: 600 }} loading={isPending}>
          ✗ Rechazar
        </button>
        <button onClick={() => mutate({ approved: true })} disabled={isPending}
          style={{ background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 8, padding: '9px 18px', color: 'var(--success)', cursor: 'pointer', fontFamily: 'inherit', fontSize: "var(--text-base)", fontWeight: 600 }} loading={isPending}>
          ✓ Aprobar
        </button>
      </div>
    </Modal>
  )
}

// ── Tab: Mis gastos ───────────────────────────────────────────────────────────
function MyExpenses() {
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')
  const [catFilter, setCatFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const { data: raw = [], isLoading } = useQuery({
    queryKey: ['expenses-my', statusFilter],
    queryFn: () => expensesApi.my({ status: statusFilter || undefined }).then(r => r.data?.items ?? r.data ?? []),
  })
  const expenses = Array.isArray(raw) ? raw : []
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
  const dateInput = (val) => ({ background: val ? 'var(--accent-muted)' : 'var(--surface-2)', border: `1px solid ${val ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 8, padding: '8px 12px', color: val ? 'var(--accent)' : 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit', outline: 'none' })
  const hasFilter = search || statusFilter || catFilter || dateFrom || dateTo

  const { mutate: submit, isPending: saving } = useMutation({
    mutationFn: id => expensesApi.submitMy(id),
    onSuccess: () => { qc.invalidateQueries(['expenses-my']); qc.invalidateQueries(['expenses-pending']); },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: recall } = useMutation({
    mutationFn: id => expensesApi.recall(id),
    onSuccess: () => { qc.invalidateQueries(['expenses-my']); qc.invalidateQueries(['expenses-pending']); },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: del } = useMutation({
    mutationFn: id => expensesApi.deleteMy(id),
    onSuccess: () => qc.invalidateQueries(['expenses-my']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const total = expenses.reduce((s, e) => s + (Number(e.amount) || 0), 0)
  const pending = expenses.filter(e => e.status === 'submitted').length

  return (
    <div>
      <div style={{ display: 'flex', gap: 14, marginBottom: 20, alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 12 }}>
          {[
            { label: 'Total', value: fmt(total), color: 'var(--text-1)' },
            { label: 'Pendientes', value: pending, color: pending > 0 ? 'var(--warning)' : 'var(--text-2)' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ ...card, padding: '10px 16px', minWidth: 120 }}>
              <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 800, color }}>{value}</div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{label}</div>
            </div>
          ))}
        </div>
        <Button onClick={() => setShowCreate(true)} style={{ marginLeft: 'auto' }}>＋ Nuevo gasto</Button>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 14 }}>
        <SearchInput value={search} onChange={setSearch} placeholder="Buscar código o descripción..." style={{ minWidth: 220, flex: '1 1 220px', maxWidth: 320 }} />
        <FilterSelect value={statusFilter} onChange={setStatusFilter} placeholder="Estado" options={Object.entries(STATUSES).map(([v, c]) => ({ value: v, label: c.label }))} />
        <FilterSelect value={catFilter} onChange={setCatFilter} placeholder="Tipo" options={Object.entries(CATEGORIES).map(([v, c]) => ({ value: v, label: `${c.icon} ${c.label}` }))} />
        <input type="date" aria-label="Desde" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={dateInput(dateFrom)} />
        <span style={{ color: 'var(--text-3)' }}>—</span>
        <input type="date" aria-label="Hasta" value={dateTo} onChange={e => setDateTo(e.target.value)} style={dateInput(dateTo)} />
        {hasFilter && (
          <button onClick={() => { setSearch(''); setStatusFilter(''); setCatFilter(''); setDateFrom(''); setDateTo('') }}
            style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-2)', fontSize: 'var(--text-sm)', cursor: 'pointer', fontFamily: 'inherit' }}>Limpiar</button>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{sortedExpenses.length} / {expenses.length}</span>
      </div>

      {isLoading ? <Spinner /> : expenses.length === 0 ? (
        <EmptyState icon="💸" title="Sin gastos" description="Crea tu primer gasto para empezar a registrarlos." />
      ) : sortedExpenses.length === 0 ? (
        <EmptyState icon="🔍" title="Sin resultados" description="Ningún gasto coincide con los filtros aplicados." />
      ) : (
        <div style={{ ...card, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '80px 110px 1fr 120px 110px 130px auto', gap: 12, padding: '10px 18px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
            <SortableTH col="code" sort={expSort} onSort={setExpSort}>#</SortableTH>
            <SortableTH col="category" sort={expSort} onSort={setExpSort}>Tipo</SortableTH>
            <SortableTH col="description" sort={expSort} onSort={setExpSort}>Descripción</SortableTH>
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
                    style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>✏</button>
                  <button onClick={() => submit(exp.id)} title="Enviar gasto" aria-label="Enviar gasto"
                    style={{ background: 'var(--warning-bg)', border: '1px solid var(--warning-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--warning)', cursor: 'pointer', fontSize: "var(--text-sm)" }} loading={saving}>↑ Enviar</button>
                  <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar este gasto?', onConfirm: () => del(exp.id), danger: true }) }} title="Eliminar gasto" aria-label="Eliminar gasto"
                    style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>🗑</button>
                </>}
                {exp.status === 'submitted' && (
                  <button onClick={() => recall(exp.id)} title="Retirar gasto" aria-label="Retirar gasto"
                    style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>↩ Retirar</button>
                )}
                {exp.status === 'rejected' && (
                  <button onClick={() => setEditing(exp)} title="Editar gasto rechazado" aria-label="Editar gasto rechazado"
                    style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>✏ Editar</button>
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
  const toast = useToast()
  const qc = useQueryClient()
  const [reviewing, setReviewing] = useState(null)

  const { data: raw = [], isLoading } = useQuery({
    queryKey: ['expenses-pending'],
    queryFn: () => expensesApi.pending().then(r => r.data),
    refetchInterval: 30000,
  })
  const expenses = Array.isArray(raw) ? raw : []
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
  const dateInput = (val) => ({ background: val ? 'var(--accent-muted)' : 'var(--surface-2)', border: `1px solid ${val ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 8, padding: '8px 12px', color: val ? 'var(--accent)' : 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit', outline: 'none' })
  const hasFilter = pendSearch || pendCat || pendFrom || pendTo

  const { mutate: _reimburse } = useMutation({
    mutationFn: id => expensesApi.reimburse(id),
    onSuccess: () => qc.invalidateQueries(['expenses-pending']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div>
      <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginBottom: 16 }}>
        {expenses.length > 0 ? `${expenses.length} gasto(s) pendientes de revisión · ${fmt(expenses.reduce((s, e) => s + (Number(e.amount) || 0), 0))} total` : 'No hay gastos pendientes'}
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 14 }}>
        <SearchInput value={pendSearch} onChange={setPendSearch} placeholder="Buscar código, descripción o solicitante..." style={{ minWidth: 240, flex: '1 1 240px', maxWidth: 360 }} />
        <FilterSelect value={pendCat} onChange={setPendCat} placeholder="Tipo" options={Object.entries(CATEGORIES).map(([v, c]) => ({ value: v, label: `${c.icon} ${c.label}` }))} />
        <input type="date" aria-label="Desde" value={pendFrom} onChange={e => setPendFrom(e.target.value)} style={dateInput(pendFrom)} />
        <span style={{ color: 'var(--text-3)' }}>—</span>
        <input type="date" aria-label="Hasta" value={pendTo} onChange={e => setPendTo(e.target.value)} style={dateInput(pendTo)} />
        {hasFilter && (
          <button onClick={() => { setPendSearch(''); setPendCat(''); setPendFrom(''); setPendTo('') }}
            style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-2)', fontSize: 'var(--text-sm)', cursor: 'pointer', fontFamily: 'inherit' }}>Limpiar</button>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{sortedPending.length} / {expenses.length}</span>
      </div>
      {isLoading ? <Spinner /> : expenses.length === 0 ? (
        <EmptyState icon="✅" title="Sin pendientes" description="No hay gastos pendientes de revisión." />
      ) : sortedPending.length === 0 ? (
        <EmptyState icon="🔍" title="Sin resultados" description="Ningún gasto pendiente coincide con los filtros aplicados." />
      ) : (
        <div style={{ ...card, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '80px 110px 1fr 120px 110px 130px auto', gap: 12, padding: '10px 18px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
            <SortableTH col="code" sort={pendSort} onSort={setPendSort}>#</SortableTH>
            <SortableTH col="category" sort={pendSort} onSort={setPendSort}>Tipo</SortableTH>
            <SortableTH col="description" sort={pendSort} onSort={setPendSort}>Descripción</SortableTH>
            <SortableTH col="amount" sort={pendSort} onSort={setPendSort}>Importe</SortableTH>
            <SortableTH col="status" sort={pendSort} onSort={setPendSort}>Estado</SortableTH>
            <SortableTH col="expense_date" sort={pendSort} onSort={setPendSort}>Solicitante</SortableTH>
            <span></span>
          </div>
          {sortedPending.map(e => (
            <ExpenseRow key={e.id} expense={e} isManager onAction={(exp) => (
              <div style={{ display: 'flex', gap: 5 }}>
                <button onClick={() => setReviewing(exp)}
                  style={{ background: 'var(--warning-bg)', border: '1px solid var(--warning-border)', borderRadius: 6, padding: '3px 10px', color: 'var(--warning)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>
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
  const toast = useToast()
  const [projectFilter, setProjectFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [_period, _setPeriod] = useState('')

  const { data: projRaw = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data) })
  const projects = Array.isArray(projRaw) ? projRaw : []

  const { data: raw, isLoading } = useQuery({
    queryKey: ['expenses-team', projectFilter, statusFilter],
    queryFn: () => expensesApi.team({ project_id: projectFilter || undefined, status: statusFilter || undefined }).then(r => r.data),
  })

  const expenses = raw?.expenses || []
  const { sort: teamSort, setSort: setTeamSort, sortedData: sortedTeam } = useSort(expenses, 'expense_date', 'desc')
  const total = raw?.total || 0
  const billable = raw?.billable_total || 0
  const byCat = raw?.by_category || {}

  const catChartData = Object.entries(byCat).map(([k, v]) => ({
    name: CATEGORIES[k]?.label || k,
    value: v,
    color: CATEGORIES[k]?.color || 'var(--text-2)',
  }))

  const qcTeam = useQueryClient()
  const { mutate: reimburse } = useMutation({
    mutationFn: id => expensesApi.reimburse(id),
    onSuccess: () => qcTeam.invalidateQueries(['expenses-team']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
        <select value={projectFilter} onChange={e => setProjectFilter(e.target.value)} style={{ ...fs, width: 'auto' }}>
          <option value="">Todos los proyectos</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
        </select>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ ...fs, width: 'auto' }}>
          <option value="">Todos los estados</option>
          {Object.entries(STATUSES).map(([v, c]) => <option key={v} value={v}>{c.label}</option>)}
        </select>
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 24 }}>
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
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
          <div style={{ ...card, padding: '16px 20px' }}>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>Por categoría</div>
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
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>Distribución</div>
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
        <EmptyState icon="💸" title="Sin gastos del equipo" description="No hay gastos para los filtros seleccionados." />
      ) : (
        <div style={{ ...card, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '80px 110px 1fr 120px 110px 130px auto', gap: 12, padding: '10px 18px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
            <SortableTH col="code" sort={teamSort} onSort={setTeamSort}>#</SortableTH>
            <SortableTH col="category" sort={teamSort} onSort={setTeamSort}>Tipo</SortableTH>
            <SortableTH col="description" sort={teamSort} onSort={setTeamSort}>Descripción</SortableTH>
            <SortableTH col="amount" sort={teamSort} onSort={setTeamSort}>Importe</SortableTH>
            <SortableTH col="status" sort={teamSort} onSort={setTeamSort}>Estado</SortableTH>
            <SortableTH col="expense_date" sort={teamSort} onSort={setTeamSort}>Revisión</SortableTH>
            <span></span>
          </div>
          {sortedTeam.map(e => (
            <ExpenseRow key={e.id} expense={e} isManager onAction={(exp) => (
              <div>
                {exp.status === 'approved' && (
                  <button onClick={() => reimburse(exp.id)}
                    style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border-strong)', borderRadius: 6, padding: '3px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>
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
export default function ExpensesPage() {
  const t = useAppT()
  const { hasRole } = useAuth()
  const isManager = hasRole('admin', 'pm', 'hr')
  const [tab, setTab] = useState('my')

  const TABS = [
    { id: 'my', label: 'Mis gastos' },
    ...(isManager ? [
      { id: 'pending', label: '⏳ Pendientes aprobación' },
      { id: 'team', label: 'Equipo' },
    ] : []),
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
            onClick={() => {
              const url = new URL('/api/v1/expenses/export', window.location.origin)
              window.open(url.toString(), '_blank')
            }}
            style={{ display: 'flex', alignItems: 'center', gap: 6,
              background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
              borderRadius: 8, padding: '8px 14px', color: 'var(--text-1)',
              cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', fontWeight: 600 }}>
            📊 Exportar Excel
          </button>
        }
      />
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 , borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ padding: '5px 14px', borderRadius: 6, border: `1px solid ${tab === t.id ? 'var(--accent)' : 'var(--surface-4)'}`, background: tab === t.id ? 'var(--accent-muted)' : 'transparent', color: tab === t.id ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'my'      && <MyExpenses />}
      {tab === 'pending' && <PendingApproval />}
      {tab === 'team'    && <TeamExpenses />}
    </PageShell>
  )
}
