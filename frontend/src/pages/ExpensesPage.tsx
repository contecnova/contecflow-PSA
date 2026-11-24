/**
 * ExpensesPage — gestión completa de gastos con flujo de aprobación
 * Vistas: Mis gastos | Pendientes aprobación | Equipo
 *
 * Fase 2 (rev. 166): las tres listas se paginan en el servidor (page/page_size;
 * total en meta.total o X-Total-Count) con búsqueda, categoría, fechas y orden
 * también en el servidor; los totales salen de `/my/totals`, `/pending/totals`
 * y del propio `/team`, así que no dependen de la página cargada. Estilos en
 * ExpensesPage.css y textos en i18n (`expenses.*`).
 */
import { useState, useId, useRef } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, localeActivo, downloadBlob, fmtDate } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { keepPreviousData, useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { expensesApi, gastosApi } from '../services/api'
import { useListaDeProyectos } from '../hooks/useListas'
import { sanitizeUrl } from '../utils/security'
import type { FiltrosDeGastos, GastoConPoliticas } from '../services/api/gastos'
import { Button, Modal, Spinner, EmptyState, useSort, SortableTH, Buscador, FilterSelect, KpiCard, Tabs, IconButton, Pulsable, Select, Checkbox, useErroresDeCampo, Input, Textarea } from '../components/ui'
import Pagination from '../components/ui/Pagination'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import {
  BedDouble, CheckCircle2, Clock, FileSpreadsheet, FileText, GraduationCap, Handshake, Laptop, Lock, Monitor,
  Package, Paperclip, Pencil, Plane, Plus, Receipt, ScanLine, Search, Send, Trash2, Undo2, User, Users, Utensils, Wallet, XCircle,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useAppLang, useAppT } from '../i18n/AppLangContext'
import { Link } from 'react-router-dom'
import { CODIGOS_DE_PAIS, nombreDePais } from '../constants/paises'
import { useOrgSettings } from '../hooks/useOrgSettings'
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer
} from 'recharts'
import DetalleDeGasto from '../components/gastos/DetalleDeGasto'
import VistaPreviaDeEnvio from '../components/gastos/VistaPreviaDeEnvio'
import IndicadorDePolitica from '../components/politicas/IndicadorDePolitica'
import DsBadge from '../components/ui/StatusBadge'
import DateInput from '../components/ui/DateInput'
import { POLL_FREQUENT_MS } from '../constants/timings'
import { useCatalogo } from '../hooks/useCatalogo'
import './ExpensesPage.css'

// ── Config ────────────────────────────────────────────────────────────────────
/** Icono y color de cada categoría; el nombre sale de i18n (`expenses.cat_<clave>`). */
const CATEGORIES: Record<string, { Icon: LucideIcon; color: string }> = {
  travel:        { Icon: Plane, color: 'var(--accent)' },
  accommodation: { Icon: BedDouble, color: 'var(--purple)' },
  meals:         { Icon: Utensils, color: 'var(--warning)' },
  software:      { Icon: Laptop, color: 'var(--success)' },
  hardware:      { Icon: Monitor, color: 'var(--warning)' },
  training:      { Icon: GraduationCap, color: 'var(--danger)' },
  subcontract:   { Icon: Handshake, color: 'var(--purple)' },
  other:         { Icon: Package, color: 'var(--text-2)' },
}
const STATUSES: Record<string, string> = {
  draft: 'var(--text-2)', submitted: 'var(--warning)', approved: 'var(--success)',
  rejected: 'var(--danger)', reimbursed: 'var(--accent)',
}
/** Filas por página de las tres listas. */
const POR_PAGINA = 25
/** Tooltip de recharts: es una prop del gráfico (no un `style`), con tokens. */
const TOOLTIP: CSSProperties = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, fontSize: 'var(--text-xs)' }
const EJE = { fontSize: 'var(--text-2xs)', fill: 'var(--text-2)' }

function useEtiquetas() {
  const t = useAppT()
  // 19-11-2026: las categorías son el catálogo de la empresa (`/settings/expense-categories`);
  // las del sistema se traducen con `expenses.cat_<clave>`, las propias llevan su etiqueta.
  const cats = useCatalogo('expense-categories')
  return {
    categoria: cats.etiqueta,
    categorias: cats.opciones,
    estado: (s: string) => t(`expenses.st_${s}`, s),
  }
}

/** Etiqueta y color de una categoría (los colores de las propias, del catálogo). */
function useEtiquetasConColor() {
  const cats = useCatalogo('expense-categories')
  return { categoria: cats.etiqueta, color: cats.color }
}

function StatusBadge({ status }: { status: string }) {
  const { estado } = useEtiquetas()
  return <DsBadge color={STATUSES[status] ?? 'var(--text-2)'} caps={false}>{estado(status)}</DsBadge>
}

function CatBadge({ cat }: { cat: string }) {
  const { categoria, color: colorDeCategoria } = useEtiquetasConColor()
  const cfg = CATEGORIES[cat] ?? { ...CATEGORIES.other, color: colorDeCategoria(cat) }
  return <DsBadge color={cfg.color} caps={false}><cfg.Icon size={11} aria-hidden /> {categoria(cat)}</DsBadge>
}

function fmt(amount: unknown, currency?: string | null) {
  const v = Number(amount).toLocaleString(localeActivo(), { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return currency ? `${v} ${currency}` : v
}

type Expense = GastoConPoliticas
type Orden = { key: string; dir: 'asc' | 'desc' }

/** Paginación, orden y filtros comunes de las tres listas (todo va al servidor). */
function useListaPaginada(ordenInicial: string, dirInicial: 'asc' | 'desc') {
  const [page, setPage] = useState(1)
  const { sort, setSort } = useSort<Expense>([], ordenInicial, dirInicial)
  const ordenar = (k: string) => { setSort(k); setPage(1) }
  const conFiltro = <T,>(setter: (v: T) => void) => (v: T) => { setter(v); setPage(1) }
  const parametros = (extra: Partial<FiltrosDeGastos>): FiltrosDeGastos => ({
    ...extra, sort: (sort as Orden).key || undefined, direction: (sort as Orden).dir, page, page_size: POR_PAGINA,
  })
  return { page, setPage, sort, ordenar, conFiltro, parametros }
}

function Paginas({ page, total, onChange }: { page: number; total: number; onChange: (p: number) => void }) {
  return (
    <div className="exp-paginacion">
      <Pagination page={page} totalPages={Math.max(1, Math.ceil(total / POR_PAGINA))} onChange={onChange}
        total={total} pageSize={POR_PAGINA} />
    </div>
  )
}

function FiltroDeFecha({ valor, onChange, etiqueta }: { valor: string; onChange: (v: string) => void; etiqueta: string }) {
  return <DateInput aria-label={etiqueta} value={valor} onChange={e => onChange(e.target.value)}
    className={`exp-fecha${valor ? ' exp-fecha--activa' : ''}`} />
}

// ── Expense row ───────────────────────────────────────────────────────────────
function ExpenseRow({ expense, onAction, isManager }: { expense: Expense; onAction?: (exp: Expense) => ReactNode; isManager?: boolean }) {
  const t = useAppT()
  const [detalle, setDetalle] = useState(false)
  return (
    <div className="exp-fila" role="row">
      <span className="u-text3-mono-xs" role="cell">{expense.code}</span>
      <span role="cell"><CatBadge cat={expense.category || ''} /></span>
      <div role="cell">
        <Pulsable type="button" onClick={() => setDetalle(true)} title={t('gas.abrir_detalle')} className="exp-descripcion">
          {expense.description}
        </Pulsable>
        {' '}<IndicadorDePolitica resumen={expense.policy_summary} />
        <div className="u-text2-xs-mt2">
          {expense.project_name || t('expenses.sin_proyecto')} · {fmtDate(expense.expense_date)}
          {isManager && <span className="exp-separado">· {expense.user_name}</span>}
        </div>
        {expense.receipt_url && (
          <a href={sanitizeUrl(expense.receipt_url)} target="_blank" rel="noopener noreferrer" onClick={ev => ev.stopPropagation()} className="exp-enlace">
            <Paperclip size={12} aria-hidden /> {t('expenses.receipt')}
          </a>
        )}
      </div>
      <span role="cell" className={`exp-importe${expense.is_billable ? ' exp-importe--facturable' : ''}`}>
        {fmt(expense.amount, expense.currency)}
        {expense.is_billable && <span className="exp-importe__nota">{t('expenses.facturable_min')}</span>}
      </span>
      <span role="cell"><StatusBadge status={expense.status || ''} /></span>
      <div className="u-text3-xs" role="cell">
        {expense.status === 'submitted' && expense.submitted_at && t('expenses.enviado_el', { fecha: fmtDate(expense.submitted_at) })}
        {expense.status === 'approved' && expense.reviewed_by_name && <span className="exp-dato"><CheckCircle2 size={12} aria-hidden /> {expense.reviewed_by_name}</span>}
        {expense.status === 'rejected' && <span className="u-danger">{expense.rejection_reason}</span>}
        {expense.status === 'reimbursed' && expense.reimbursed_at && <span className="exp-dato"><Wallet size={12} aria-hidden /> {fmtDate(expense.reimbursed_at)}</span>}
      </div>
      <div className="u-row-6" role="cell">
        {onAction && onAction(expense)}
      </div>
      {detalle && <DetalleDeGasto gasto={expense} editable={expense.status === 'draft' || !!isManager} onClose={() => setDetalle(false)} />}
    </div>
  )
}

function Cabecera({ sort, onSort, ultima }: { sort: Orden; onSort: (k: string) => void; ultima: string }) {
  const t = useAppT()
  return (
    <div className="exp-fila exp-fila--cabecera" role="row">
      <SortableTH col="code" sort={sort} onSort={onSort}>#</SortableTH>
      <SortableTH col="category" sort={sort} onSort={onSort}>{t('expenses.tipo')}</SortableTH>
      <SortableTH col="description" sort={sort} onSort={onSort}>{t('expenses.descripcion_2')}</SortableTH>
      <SortableTH col="amount" sort={sort} onSort={onSort}>{t('expenses.amount')}</SortableTH>
      <SortableTH col="status" sort={sort} onSort={onSort}>{t('expenses.estado')}</SortableTH>
      <SortableTH col="expense_date" sort={sort} onSort={onSort}>{ultima}</SortableTH>
      <span />
    </div>
  )
}

// ── Create/Edit expense modal ─────────────────────────────────────────────────
function ExpenseModal({ expense, onClose }: { expense?: Expense; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const { categorias } = useEtiquetas()
  const qc = useQueryClient()
  const toast = useToast()
  const { currency: defaultCurrency, currencies: monedasDeLaEmpresa } = useOrgSettings()
  const isEdit = !!expense
  const [ocrLoading, setOcrLoading] = useState(false)
  const ficheroOcr = useRef<HTMLInputElement | null>(null)
  const [form, setForm] = useState<{
    project_id: string; category: string; description: string; amount: string | number;
    currency: string; expense_date: string; is_billable: boolean; notes: string; km: string
    country: string; city: string; attendees: string; trip: string
  }>({
    project_id:  expense?.project_id  || '',
    category:    expense?.category    || 'travel',
    description: expense?.description || '',
    amount:      expense?.amount ?? '',
    currency:    expense?.currency    || defaultCurrency,
    expense_date: expense?.expense_date || new Date().toISOString().slice(0, 10),
    is_billable: expense?.is_billable ?? true,
    notes:       expense?.notes       || '',
    km:          expense?.km ? String(expense.km) : '',
    country:     expense?.country     || '',
    city:        expense?.city        || '',
    attendees:   expense?.attendees ? String(expense.attendees) : '',
    trip:        expense?.trip        || '',
  })
  const { lang } = useAppLang()
  const paises = [...CODIGOS_DE_PAIS].sort((a, b) => nombreDePais(a, lang).localeCompare(nombreDePais(b, lang)))
  // Ciudades y viajes que ya usó esta persona (lo que hay en caché de sus listas): se eligen, no se reescriben.
  const previos: Expense[] = qc.getQueriesData<{ items: Expense[] }>({ queryKey: ['expenses-my'] })
    .flatMap(([, d]) => d?.items ?? [])
  const ciudades = [...new Set(previos.filter(e => e.city && (!form.country || e.country === form.country)).map(e => e.city as string))].sort()
  const viajes = [...new Set(previos.map(e => e.trip).filter(Boolean) as string[])].sort()
  const campos = useErroresDeCampo()
  const set = (k: string) => (e: { target: { value: string } }) => { campos.limpiar(k); setForm(f => ({ ...f, [k]: e.target.value })) }
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null

  // 23-11-2026 (04 A8): lista compartida de proyectos.
  const { data: projects = [] } = useListaDeProyectos()

  const { mutate, isPending } = useMutation({
    mutationFn: (d: Record<string, unknown>) => isEdit ? expensesApi.updateMy(expense!.id, d) : expensesApi.create(d),
    onMutate: () => campos.limpiar(),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['expenses-my'] }); qc.invalidateQueries({ queryKey: ['expenses-pending'] }); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('expenses.error_guardar'))) },
  })
  const id = (k: string) => `${idCampo}-${k}`

  return (
    <Modal open title={isEdit ? t('expenses.editar_gasto') : t('expenses.new_expense')} onClose={onClose} width={580}>
      {!isEdit && (
        <div className="exp-ocr">
          <span className="exp-ocr__icono" aria-hidden><ScanLine size={22} /></span>
          <div className="exp-ocr__texto">
            <div className="exp-ocr__titulo">{t('expenses.escanear_recibo_con_ia')}</div>
            <div className="u-text2-xs">{t('expenses.sube_una_foto_o_pdf_y_el')}</div>
          </div>
          <div className="exp-ocr__subir">
            <input ref={ficheroOcr} type="file" hidden accept="image/*,.pdf" aria-label={t('expenses.escanear_recibo_con_ia')} onChange={async e => {
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
                  description:  ex.description || (ex.merchant ? t('expenses.gasto_en', { comercio: ex.merchant }) : f.description),
                  expense_date: ex.date    ?? f.expense_date,
                  category:     ex.category ?? f.category,
                }))
                toast.success(t('expenses.recibo_escaneado'))
              } catch (err) {
                toast.error(extractErr(err, t('expenses.error_escanear')))
              } finally {
                setOcrLoading(false)
                e.target.value = ''
              }
            }} />
            <Button variant="secondary" icon={<Paperclip size={14} />} loading={ocrLoading} onClick={() => ficheroOcr.current?.click()}>
              {ocrLoading ? t('expenses.analizando') : t('expenses.subir_recibo')}
            </Button>
          </div>
        </div>
      )}
      <div className="u-grid2-14">
        <div className="u-col-full ds-field">
          <label htmlFor={id('desc')} className="ds-field__label">{t('expenses.descripcion')}</label>
          <Input id={id('desc')} value={form.description} onChange={set('description')} placeholder={t('expenses.descripcion_del_gasto')} />
          {msg('description')}
        </div>
        <div className="ds-field">
          <label htmlFor={id('cat')} className="ds-field__label">{t('expenses.category')}</label>
          <Select suelto placeholder={false} id={id('cat')} value={form.category} onChange={set('category')} className="ds-input">
            {categorias.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
          {msg('category')}
        </div>
        <div className="ds-field">
          <label htmlFor={id('proy')} className="ds-field__label">{t('expenses.proyecto')}</label>
          <Select suelto placeholder={false} id={id('proy')} value={form.project_id} onChange={set('project_id')} className="ds-input">
            <option value="">{t('expenses.sin_proyecto')}</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </Select>
          {msg('project_id')}
        </div>
        <div className="ds-field">
          <label htmlFor={id('imp')} className="ds-field__label">{t('expenses.importe_obligatorio')}</label>
          <Input id={id('imp')} type="number" step="0.01" value={form.km ? '' : form.amount} disabled={!!form.km} onChange={set('amount')} placeholder={form.km ? t('gas.importe_por_km') : t('expenses.amount')} />
          {msg('amount')}
        </div>
        <div className="ds-field">
          <label htmlFor={id('km')} className="ds-field__label">{t('gas.km')}</label>
          <Input id={id('km')} type="number" step="0.1" min={0} value={form.km} onChange={set('km')} placeholder={t('gas.km_ayuda')} />
          {msg('km')}
        </div>
        <div className="ds-field">
          <label htmlFor={id('mon')} className="ds-field__label">{t('expenses.currency')}</label>
          <Select suelto placeholder={false} id={id('mon')} value={form.currency} onChange={set('currency')} className="ds-input">
            {monedasDeLaEmpresa.map(c => <option key={c} value={c}>{c}</option>)}
          </Select>
          {msg('currency')}
        </div>
        <div className="ds-field">
          <label htmlFor={id('fecha')} className="ds-field__label">{t('expenses.fecha_del_gasto')}</label>
          <DateInput id={id('fecha')} value={form.expense_date} onChange={set('expense_date')} className="ds-input" />
          {msg('expense_date')}
        </div>
        <div className="ds-field">
          <label htmlFor={id('pais')} className="ds-field__label">{t('gas.pais')}</label>
          <Select suelto placeholder={false} id={id('pais')} value={form.country} onChange={set('country')} className="ds-input">
            <option value="">{t('gas.sin_pais')}</option>
            {paises.map(c => <option key={c} value={c}>{nombreDePais(c, lang)} ({c})</option>)}
          </Select>
          {msg('country')}
        </div>
        <div className="ds-field">
          <label htmlFor={id('ciudad')} className="ds-field__label">{t('gas.ciudad')}</label>
          <Input id={id('ciudad')} list={id('ciudades')} value={form.city} onChange={set('city')} maxLength={120} />
          {msg('city')}
          <datalist id={id('ciudades')}>{ciudades.map(c => <option key={c} value={c} aria-label={c} />)}</datalist>
        </div>
        {form.category === 'meals' && (
          <div className="ds-field">
            <label htmlFor={id('asis')} className="ds-field__label">{t('gas.asistentes')}</label>
            <Input id={id('asis')} type="number" min={1} step={1} value={form.attendees} onChange={set('attendees')} aria-describedby={id('asis-ayuda')} />
          {msg('attendees')}
            <span id={id('asis-ayuda')} className="ds-field__hint">{t('gas.asistentes_ayuda')}</span>
          </div>
        )}
        <div className="ds-field">
          <label htmlFor={id('viaje')} className="ds-field__label">{t('gas.viaje')}</label>
          <Input id={id('viaje')} list={id('viajes')} value={form.trip} onChange={set('trip')} maxLength={120} aria-describedby={id('viaje-ayuda')} />
          {msg('trip')}
          <datalist id={id('viajes')}>{viajes.map(c => <option key={c} value={c} aria-label={c} />)}</datalist>
          <span id={id('viaje-ayuda')} className="ds-field__hint">{t('gas.viaje_ayuda')}</span>
        </div>
        <div className="exp-check">
          <Checkbox id={id('fact')} checked={form.is_billable} onChange={(_, e) => setForm(f => ({ ...f, is_billable: e.target.checked }))} />
          <label htmlFor={id('fact')}>{t('expenses.gasto_facturable_al_cliente')}</label>
        </div>
        <div className="u-col-full ds-field">
          <label htmlFor={id('notas')} className="ds-field__label">{t('expenses.notas_adicionales')}</label>
          <Textarea id={id('notas')} value={form.notes} onChange={set('notes')} rows={2} placeholder={t('expenses.notas_adicionales')} inputClassName="exp-textarea" />
          {msg('notes')}
        </div>
        <div className="exp-nota">{t('gas.justificantes_en_el_detalle')}</div>
        <div className="exp-pie">
          <Button variant="secondary" onClick={onClose}>{t('expenses.cancelar')}</Button>
          <Button onClick={() => {
            const { km, attendees, ...resto } = form
            const base = { ...resto, attendees: form.category === 'meals' && attendees ? Number(attendees) : null }
            mutate(km ? { ...base, km: Number(km), amount: Number(resto.amount) || 0 } : base)
          }}
            disabled={isPending || !form.description || (!form.amount && !form.km) || !form.expense_date} loading={isPending}>
            {isPending ? t('expenses.guardando') : isEdit ? t('expenses.guardar_cambios') : t('expenses.crear_gasto')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Review modal ──────────────────────────────────────────────────────────────
function ReviewModal({ expense, onClose }: { expense: Expense; onClose: () => void }) {
  const t = useAppT()
  const idCampo = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const [reason, setReason] = useState('')
  const { mutate, isPending } = useMutation({
    mutationFn: (d: Record<string, unknown>) => expensesApi.review(expense.id, d),
    onSuccess: (r) => {
      // Control presupuestario (BUDGET_CONTROL_POLICY = avisar): se aprueba, y se dice de qué presupuesto se pasa.
      for (const aviso of r.data.avisos_de_presupuesto) toast.warning(aviso, 8000)
      qc.invalidateQueries({ queryKey: ['expenses-pending'] }); qc.invalidateQueries({ queryKey: ['expenses-team'] }); onClose()
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('expenses.error_revisar'))),
  })
  return (
    <Modal open title={t('expenses.revisar_gasto', { code: expense.code ?? '' })} onClose={onClose} width={480}>
      <div className="exp-revision">
        <div className="exp-revision__titulo">{expense.description}</div>
        <div className="exp-revision__datos">
          <span className="exp-dato"><User size={13} aria-hidden /> {expense.user_name}</span>
          <span><CatBadge cat={expense.category || ''} /></span>
          <span className="exp-revision__importe">{fmt(expense.amount, expense.currency)}</span>
        </div>
        {expense.notes && <div className="exp-revision__notas">{expense.notes}</div>}
        {expense.receipt_url && (
          <a href={sanitizeUrl(expense.receipt_url)} target="_blank" rel="noopener noreferrer" className="exp-enlace">
            <Paperclip size={12} aria-hidden /> {t('expenses.ver_justificante')}
          </a>
        )}
      </div>
      <div className="u-mb-16 ds-field">
        <label htmlFor={`${idCampo}-motivo`} className="ds-field__label">{t('expenses.motivo_de_rechazo_si_aplica')}</label>
        <Input id={`${idCampo}-motivo`} value={reason} onChange={e => setReason(e.target.value)} placeholder={t('expenses.motivo_de_rechazo')} />
      </div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>{t('expenses.cancelar')}</Button>
        <Button variant="danger" icon={<XCircle size={14} />} onClick={() => mutate({ approved: false, rejection_reason: reason })} disabled={isPending || !reason}>
          {t('expenses.rechazar')}</Button>
        <Button icon={<CheckCircle2 size={14} />} onClick={() => mutate({ approved: true })} disabled={isPending}>
          {t('expenses.approve')}</Button>
      </div>
    </Modal>
  )
}

// ── Tab: Mis gastos ───────────────────────────────────────────────────────────
function MyExpenses({ showCreate, setShowCreate }: { showCreate: boolean; setShowCreate: (v: boolean) => void }) {
  const t = useAppT()
  const { estado, categorias } = useEtiquetas()
  const toast = useToast()
  const qc = useQueryClient()
  const [editing, setEditing] = useState<Expense | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')
  const [catFilter, setCatFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const lista = useListaPaginada('expense_date', 'desc')
  const filtros = { status: statusFilter, category: catFilter, q: search, date_from: dateFrom, date_to: dateTo }

  const q = useQuery({
    queryKey: ['expenses-my', filtros, lista.sort, lista.page],
    queryFn: () => gastosApi.mios(lista.parametros(filtros)),
    placeholderData: keepPreviousData,
  })
  const totales = useQuery({ queryKey: ['expenses-my', 'totales', filtros], queryFn: () => gastosApi.totalesMios(filtros) })
  const expenses = q.data?.items ?? []
  const hasFilter = search || statusFilter || catFilter || dateFrom || dateTo

  const [confirmando, setConfirmando] = useState<Expense | null>(null)
  const [detalleDe, setDetalleDe] = useState<Expense | null>(null)
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['expenses-my'] }); qc.invalidateQueries({ queryKey: ['expenses-pending'] }) }
  const { mutate: submit, isPending: saving } = useMutation({
    mutationFn: (id: string) => expensesApi.submitMy(id),
    onSuccess: () => { setConfirmando(null); refrescar() },
    onError: (e: unknown) => toast.error(extractErr(e, t('expenses.error_enviar'))),
  })
  const { mutate: recall } = useMutation({
    mutationFn: (id: string) => expensesApi.recall(id),
    onSuccess: refrescar,
    onError: (e: unknown) => toast.error(extractErr(e, t('expenses.error_retirar'))),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id: string) => expensesApi.deleteMy(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['expenses-my'] }),
    onError: (e: unknown) => toast.error(extractErr(e, t('expenses.error_eliminar'))),
  })
  const pendientes = totales.data?.submitted_count ?? 0

  return (
    <div>
      <div className="ds-grid-stats exp-kpis">
        <KpiCard icon={<Receipt size={16} />} label={t('expenses.total')} value={totales.data ? fmt(totales.data.total_amount) : '—'} />
        <KpiCard icon={<Clock size={16} />} label={t('expenses.pendientes_kpi')} value={totales.data ? pendientes : '—'} warning={pendientes > 0} />
      </div>
      <div className="exp-filtros">
        <div className="exp-busqueda"><Buscador value={search} onChange={lista.conFiltro(setSearch)} placeholder={t('expenses.buscar_codigo_o_descripcion')} /></div>
        <FilterSelect value={statusFilter} onChange={lista.conFiltro(setStatusFilter)} placeholder={t('expenses.estado')}
          options={Object.keys(STATUSES).map(v => ({ value: v, label: estado(v) }))} />
        <FilterSelect value={catFilter} onChange={lista.conFiltro(setCatFilter)} placeholder={t('expenses.tipo')}
          options={categorias} />
        <FiltroDeFecha valor={dateFrom} onChange={lista.conFiltro(setDateFrom)} etiqueta={t('expenses.desde')} />
        <span className="u-text3" aria-hidden>—</span>
        <FiltroDeFecha valor={dateTo} onChange={lista.conFiltro(setDateTo)} etiqueta={t('expenses.hasta')} />
        {hasFilter && (
          <Button size="sm" variant="ghost" onClick={() => {
            setSearch(''); setStatusFilter(''); setCatFilter(''); setDateFrom(''); setDateTo(''); lista.setPage(1)
          }}>{t('expenses.limpiar')}</Button>
        )}
      </div>

      {q.isLoading ? <Spinner /> : q.isError ? (
        <div role="alert" className="u-danger">{extractErr(q.error, t('expenses.error_cargar'))}</div>
      ) : expenses.length === 0 ? (
        hasFilter
          ? <EmptyState icon={<Search size={28} />} title={t('expenses.sin_resultados')} description={t('expenses.ningun_gasto_coincide')} />
          : <EmptyState icon={<Receipt size={28} />} title={t('expenses.sin_gastos')} description={t('expenses.crea_primer_gasto')}
              action={<Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('expenses.nuevo_gasto')}</Button>} />
      ) : (
        <>
          <div className="ds-card exp-tabla" role="table" aria-label={t('expenses.tab_mis')}>
            <Cabecera sort={lista.sort as Orden} onSort={lista.ordenar} ultima={t('expenses.info')} />
            {expenses.map(e => (
              <ExpenseRow key={e.id} expense={e} isManager={false} onAction={(exp) => (
                <div className="exp-acciones">
                  {exp.status === 'draft' && <>
                    <IconButton variante="caja" onClick={() => setEditing(exp)} ariaLabel={t('expenses.editar_gasto')}><Pencil size={14} aria-hidden /></IconButton>
                    <Button size="xs" variant="secondary" icon={<Send size={12} />} onClick={() => setConfirmando(exp)} title={t('expenses.enviar_gasto')}
                      disabled={saving}>{t('expenses.enviar')}</Button>
                    <IconButton variante="caja" tono="peligro" ariaLabel={t('expenses.eliminar_gasto')}
                      onClick={() => openConfirmGlobal({ message: t('expenses.eliminar_confirmar'), onConfirm: () => del(exp.id), danger: true })}><Trash2 size={14} aria-hidden /></IconButton>
                  </>}
                  {exp.status === 'submitted' && (
                    <Button size="xs" variant="secondary" icon={<Undo2 size={12} />} onClick={() => recall(exp.id)} title={t('expenses.retirar_gasto')}>
                      {t('expenses.retirar')}</Button>
                  )}
                  {exp.status === 'rejected' && (
                    <Button size="xs" variant="secondary" icon={<Pencil size={12} />} onClick={() => setEditing(exp)}
                      title={t('expenses.editar_rechazado')}>{t('expenses.editar')}</Button>
                  )}
                </div>
              )} />
            ))}
          </div>
          <Paginas page={lista.page} total={q.data?.total ?? 0} onChange={lista.setPage} />
        </>
      )}
      {showCreate && <ExpenseModal onClose={() => setShowCreate(false)} />}
      {editing && <ExpenseModal expense={editing} onClose={() => setEditing(null)} />}
      {confirmando && (
        <VistaPreviaDeEnvio gastoId={confirmando.id} titulo={`${confirmando.code ?? ''} — ${confirmando.description ?? ''}`}
          enviando={saving} onConfirmar={() => submit(confirmando.id)} onCerrar={() => setConfirmando(null)}
          onAbrirDetalle={() => { setDetalleDe(confirmando); setConfirmando(null) }} />
      )}
      {detalleDe && <DetalleDeGasto gasto={detalleDe} editable onClose={() => setDetalleDe(null)} />}
    </div>
  )
}

// ── Tab: Pendientes aprobación ────────────────────────────────────────────────
function PendingApproval() {
  const t = useAppT()
  const { categorias } = useEtiquetas()
  const [reviewing, setReviewing] = useState<Expense | null>(null)
  const [pendSearch, setPendSearch] = useState('')
  const [pendCat, setPendCat] = useState('')
  const [pendFrom, setPendFrom] = useState('')
  const [pendTo, setPendTo] = useState('')
  const lista = useListaPaginada('submitted_at', 'asc')
  const filtros = { category: pendCat, q: pendSearch, date_from: pendFrom, date_to: pendTo }

  const q = useQuery({
    queryKey: ['expenses-pending', filtros, lista.sort, lista.page],
    queryFn: () => gastosApi.pendientes(lista.parametros(filtros)),
    refetchInterval: POLL_FREQUENT_MS,
    placeholderData: keepPreviousData,
  })
  const totales = useQuery({ queryKey: ['expenses-pending', 'totales', filtros], queryFn: () => gastosApi.totalesPendientes(filtros),
    refetchInterval: POLL_FREQUENT_MS })
  const expenses = q.data?.items ?? []
  const hasFilter = pendSearch || pendCat || pendFrom || pendTo

  return (
    <div>
      <div className="exp-resumen" aria-live="polite">
        {totales.data && totales.data.count > 0
          ? t('expenses.pendientes_resumen', { n: totales.data.count, total: fmt(totales.data.total_amount) })
          : totales.data ? t('expenses.no_hay_pendientes') : ''}
      </div>
      <div className="exp-filtros">
        <div className="exp-busqueda"><Buscador value={pendSearch} onChange={lista.conFiltro(setPendSearch)} placeholder={t('expenses.buscar_codigo_descripcion_o_solicitante')} /></div>
        <FilterSelect value={pendCat} onChange={lista.conFiltro(setPendCat)} placeholder={t('expenses.tipo')}
          options={categorias} />
        <FiltroDeFecha valor={pendFrom} onChange={lista.conFiltro(setPendFrom)} etiqueta={t('expenses.desde')} />
        <span className="u-text3" aria-hidden>—</span>
        <FiltroDeFecha valor={pendTo} onChange={lista.conFiltro(setPendTo)} etiqueta={t('expenses.hasta')} />
        {hasFilter && (
          <Button size="sm" variant="ghost" onClick={() => {
            setPendSearch(''); setPendCat(''); setPendFrom(''); setPendTo(''); lista.setPage(1)
          }}>{t('expenses.limpiar')}</Button>
        )}
      </div>
      {q.isLoading ? <Spinner /> : q.isError ? (
        <div role="alert" className="u-danger">{extractErr(q.error, t('expenses.error_cargar'))}</div>
      ) : expenses.length === 0 ? (
        hasFilter
          ? <EmptyState icon={<Search size={28} />} title={t('expenses.sin_resultados')} description={t('expenses.ningun_pendiente_coincide')} />
          : <EmptyState icon={<CheckCircle2 size={28} />} title={t('expenses.sin_pendientes')} description={t('expenses.no_hay_pendientes_texto')} />
      ) : (
        <>
          <div className="ds-card exp-tabla" role="table" aria-label={t('expenses.tab_pendientes')}>
            <Cabecera sort={lista.sort as Orden} onSort={lista.ordenar} ultima={t('expenses.solicitante')} />
            {expenses.map(e => (
              <ExpenseRow key={e.id} expense={e} isManager onAction={(exp) => (
                <div className="exp-acciones">
                  <Button size="xs" onClick={() => setReviewing(exp)}>{t('expenses.revisar')}</Button>
                </div>
              )} />
            ))}
          </div>
          <Paginas page={lista.page} total={q.data?.total ?? 0} onChange={lista.setPage} />
        </>
      )}
      {reviewing && <ReviewModal expense={reviewing} onClose={() => setReviewing(null)} />}
    </div>
  )
}

// ── Tab: Equipo (resumen + todos) ─────────────────────────────────────────────
function TeamExpenses() {
  const t = useAppT()
  const { categoria, estado } = useEtiquetas()
  const idCampo = useId()
  const toast = useToast()
  const [projectFilter, setProjectFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const lista = useListaPaginada('expense_date', 'desc')
  const filtros = { project_id: projectFilter, status: statusFilter }

  // 23-11-2026 (04 A8): lista compartida de proyectos.
  const { data: projects = [] } = useListaDeProyectos()

  const q = useQuery({
    queryKey: ['expenses-team', filtros, lista.sort, lista.page],
    queryFn: () => gastosApi.equipo(lista.parametros(filtros)),
    placeholderData: keepPreviousData,
  })
  const expenses = q.data?.items ?? []
  const total = q.data?.importe_total ?? 0
  const billable = q.data?.facturable_total ?? 0
  const catChartData = Object.entries(q.data?.por_categoria ?? {}).map(([k, v]) => ({
    name: categoria(k), value: v, color: CATEGORIES[k]?.color || 'var(--text-2)',
  }))

  const qcTeam = useQueryClient()
  const { mutate: reimburse } = useMutation({
    mutationFn: (id: string) => expensesApi.reimburse(id),
    onSuccess: () => qcTeam.invalidateQueries({ queryKey: ['expenses-team'] }),
    onError: (e: unknown) => toast.error(extractErr(e, t('expenses.error_reembolsar'))),
  })

  return (
    <div>
      <div className="exp-filtros">
        <label htmlFor={`${idCampo}-proy`} className="u-sr-only">{t('expenses.proyecto')}</label>
        <Select suelto placeholder={false} id={`${idCampo}-proy`} value={projectFilter} onChange={e => { setProjectFilter(e.target.value); lista.setPage(1) }} className="ds-input exp-select">
          <option value="">{t('expenses.todos_los_proyectos')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
        </Select>
        <label htmlFor={`${idCampo}-est`} className="u-sr-only">{t('expenses.estado')}</label>
        <Select suelto placeholder={false} id={`${idCampo}-est`} value={statusFilter} onChange={e => { setStatusFilter(e.target.value); lista.setPage(1) }} className="ds-input exp-select">
          <option value="">{t('expenses.todos_los_estados')}</option>
          {Object.keys(STATUSES).map(v => <option key={v} value={v}>{estado(v)}</option>)}
        </Select>
      </div>

      <div className="ds-grid-stats exp-kpis-equipo">
        <KpiCard icon={<Receipt size={16} />} label={t('expenses.total_gastos')} value={fmt(total)} />
        <KpiCard icon={<FileText size={16} />} label={t('expenses.billable')} value={fmt(billable)} accent />
        <KpiCard icon={<Lock size={16} />} label={t('expenses.no_facturable')} value={fmt(total - billable)} />
        <KpiCard icon={<FileSpreadsheet size={16} />} label={t('expenses.n_gastos')} value={q.data?.total ?? 0} />
      </div>

      {catChartData.length > 0 && (
        <div className="exp-graficos">
          <div className="ds-card exp-grafico">
            <div className="exp-grafico__titulo">{t('expenses.por_categoria')}</div>
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={catChartData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} paddingAngle={2}>
                  {catChartData.map((e, i) => <Cell key={i} fill={e.color} />)}
                </Pie>
                <Tooltip formatter={v => fmt(v)} contentStyle={TOOLTIP} />
              </PieChart>
            </ResponsiveContainer>
            {catChartData.map(d => (
              <div key={d.name} className="exp-leyenda">
                <span className="exp-leyenda__nombre" style={{ '--exp-color': d.color } as CSSProperties}>● {d.name}</span>
                <span className="exp-leyenda__valor">{fmt(d.value)}</span>
              </div>
            ))}
          </div>
          <div className="ds-card exp-grafico">
            <div className="exp-grafico__titulo">{t('expenses.distribucion')}</div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={catChartData} margin={{ top: 0, right: 0, left: -10, bottom: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="name" tick={EJE} angle={-30} textAnchor="end" />
                <YAxis tick={EJE} />
                <Tooltip formatter={v => fmt(v)} contentStyle={TOOLTIP} />
                <Bar dataKey="value" radius={[3, 3, 0, 0]}>
                  {catChartData.map((e, i) => <Cell key={i} fill={e.color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {q.isLoading ? <Spinner /> : q.isError ? (
        <div role="alert" className="u-danger">{extractErr(q.error, t('expenses.error_cargar'))}</div>
      ) : expenses.length === 0 ? (
        <EmptyState icon={<Users size={28} />} title={t('expenses.sin_gastos_del_equipo')} description={t('expenses.sin_gastos_filtros')} />
      ) : (
        <>
          <div className="ds-card exp-tabla" role="table" aria-label={t('expenses.tab_equipo')}>
            <Cabecera sort={lista.sort as Orden} onSort={lista.ordenar} ultima={t('expenses.revision')} />
            {expenses.map(e => (
              <ExpenseRow key={e.id} expense={e} isManager onAction={(exp) => (
                <div>
                  {exp.status === 'approved' && (
                    <Button size="xs" variant="secondary" icon={<Wallet size={12} />} onClick={() => reimburse(exp.id)}>{t('expenses.reembolsar')}</Button>
                  )}
                </div>
              )} />
            ))}
          </div>
          <Paginas page={lista.page} total={q.data?.total ?? 0} onChange={lista.setPage} />
        </>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ExpensesPage(): JSX.Element {
  const t = useAppT()
  const { puede } = useAuth()
  const isManager = puede('gastos.gestionar')
  const toast = useToast()
  const [tab, setTab] = useState('my')
  const [creando, setCreando] = useState(false)

  const TABS = [
    { id: 'my', label: t('expenses.tab_mis'), icon: <Receipt size={14} /> },
    ...(isManager ? [
      { id: 'pending', label: t('expenses.tab_pendientes'), icon: <Clock size={14} /> },
      { id: 'team', label: t('expenses.tab_equipo'), icon: <Users size={14} /> },
    ] : []),
  ]

  return (
    <PageShell>
      <PageHeader
        icon={<Receipt size={18} />}
        title={t('nav.expenses')}
        subtitle={t('expenses.subtitle')}
        showListExport={false}
        actions={<>
          {puede('org.administrar') && <Link to="/settings/policies" className="u-text2-sm">{t('gas.politicas_de_gasto')}</Link>}
          <Button variant="secondary" icon={<FileSpreadsheet size={14} />}
            onClick={async () => {
              // Por el cliente (refresco de sesión y errores); antes abría la URL en otra pestaña.
              try {
                const r = await expensesApi.exportExcel()
                const nombre = /filename="?([^";]+)"?/.exec(String(r.headers?.['content-disposition'] ?? ''))?.[1] || 'gastos.xlsx'
                downloadBlob(r.data, nombre)
              } catch (e) {
                toast.error(extractErr(e, t('expenses.error_exportar')))
              }
            }}>
            {t('expenses.exportar_excel')}
          </Button>
          <Button icon={<Plus size={14} />} onClick={() => { setTab('my'); setCreando(true) }}>{t('expenses.nuevo_gasto')}</Button>
        </>}
      />
      {TABS.length > 1 && <Tabs items={TABS} active={tab} onChange={setTab} ariaLabel={t('nav.expenses')} className="exp-tabs" />}
      {tab === 'my'      && <MyExpenses showCreate={creando} setShowCreate={setCreando} />}
      {tab === 'pending' && <PendingApproval />}
      {tab === 'team'    && <TeamExpenses />}
    </PageShell>
  )
}
