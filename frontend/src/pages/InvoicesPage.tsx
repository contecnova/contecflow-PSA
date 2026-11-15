/**
 * InvoicesPage — Facturación: crear, gestionar y hacer seguimiento de facturas
 */
import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { extractErr, localeActivo } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, invoicesApi, accountingApi, clientsApi, unwrapList } from '../services/api'
import type { BorradorDeFacturaDesdePartes, Factura } from '../services/api/tipos-finanzas'
import { Button, Modal, Spinner, EmptyState, ClientSelect, useSort, SortableTH, Toolbar } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { CreditCard, Download } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import FichaDeFactura from '../components/invoices/FichaDeFactura'
import { alpha } from '../constants/theme'
import DateInput from '../components/ui/DateInput'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { STALE_DEFAULT_MS } from '../constants/timings'
import { ACCOUNTING_PUSH_BATCH_SIZE, SELECTOR_LIST_SIZE } from '../constants/pagination'
import './InvoicesPage.css'
interface InvoiceLine {
  description: string
  quantity: number
  unit_price: number
  amount: number
}

interface ProjectItem {
  id: string | number
  code?: string
  name?: string
  client_id?: string | number
}

interface ClientItem {
  id: string | number
  name?: string
}

type PreviewData = BorradorDeFacturaDesdePartes

interface InvoiceCreateForm {
  project_id: string
  client_id: string
  client_name: string
  client_vat: string
  client_email: string
  issue_date: string
  due_date: string
  tax_rate: number
  notes: string
  period_from: string
  period_to: string
  po_reference: string
  lines: InvoiceLine[]
}

type InvoiceStatus = 'draft' | 'sent' | 'paid' | 'overdue' | 'cancelled'

const _PALETTE = ['var(--accent)','var(--success)','var(--warning)','var(--danger)','var(--purple)','var(--warning)']


// ── Invoices Tab ──────────────────────────────────────────────────────────────
function InvoicesTab() {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()

  // ── Sync contable ────────────────────────────────────────────────────────
  const [syncProvider, setSyncProvider] = useState('xero')
  const { data: syncStatus = null } = useQuery({
    queryKey: ['accounting-sync-status'],
    queryFn: () => accountingApi.syncStatus().then(r => r.data).catch(() => null),
    staleTime: STALE_DEFAULT_MS,
  })
  // get_sync_status: la última sincronización es por integración (`xero` o `quickbooks`) y
  // los pendientes van en `invoices.pending_sync` (antes se leían `last_sync_at` y `pending_count`, que no llegan).
  const ultimaSync = syncStatus?.active_integrations.find(i => i.type === syncProvider)?.last_sync ?? null
  const pendientesDeSync = syncStatus?.invoices.pending_sync ?? 0
  const { mutate: syncBulk, isPending: syncing } = useMutation({
    mutationFn: () => accountingApi.pushBulk({ provider: syncProvider, limit: ACCOUNTING_PUSH_BATCH_SIZE }),
    onSuccess: (res) => toast.success(t('invoices.sync_success', { count: res.data.synced, provider: syncProvider })),
    onError: (e: unknown) => toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || t('invoices.sync_error')),
  })
  const [showCreate, setShowCreate] = useState(false)
  const [selectedProject, setSelectedProject] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [previewData, setPreviewData] = useState<PreviewData | null>(null)
  const [pdfLoadingId, setPdfLoadingId] = useState<string | number | null>(null)
  const [form, setForm] = useState<InvoiceCreateForm>({ project_id:'', client_id:'', client_name:'', client_vat:'', client_email:'', issue_date:new Date().toISOString().slice(0,10), due_date:'', tax_rate:21, notes:'', period_from:'', period_to:'', po_reference:'', lines:[] })

  const { data: invoices = [], isLoading } = useQuery({
    queryKey: ['invoices', selectedProject, statusFilter],
    queryFn: () => invoicesApi.list({ project_id: selectedProject || undefined, status: statusFilter || undefined }).then(r => r.data),
  })
  const { data: summary = null } = useQuery({ queryKey: ['invoice-summary'], queryFn: () => invoicesApi.summary().then(r => r.data) })
  const { data: projectsRaw = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list({}).then(unwrapList) })
  const projects = projectsRaw as ProjectItem[]
  const { data: clientsRaw = [] } = useQuery({ queryKey: ['clients'], queryFn: () => clientsApi.list({ page_size: SELECTOR_LIST_SIZE }).then(unwrapList) })
  const clients = clientsRaw as ClientItem[]

  const { mutate: create, isPending } = useMutation({
    mutationFn: (d: InvoiceCreateForm) => invoicesApi.create(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['invoices'] })
      qc.invalidateQueries({ queryKey: ['invoice-summary'] })
      qc.invalidateQueries({ queryKey: ['clients'] })
      qc.invalidateQueries({ queryKey: ['client-detail'] })
      qc.invalidateQueries({ queryKey: ['client-invoices'] })
      setShowCreate(false)
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: updateStatus } = useMutation({
    mutationFn: ({ id, status }: { id: string | number; status: InvoiceStatus }) => invoicesApi.updateStatus(id, status),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['invoices'] }); qc.invalidateQueries({ queryKey: ['invoice-summary'] }) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const downloadPdf = async (inv: Factura) => {
    setPdfLoadingId(inv.id)
    toast.info(t('invoices.pdf_generating', { number: inv.number }))
    try {
      const res = await invoicesApi.pdf(inv.id)
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      const a = document.createElement('a')
      a.href = url
      a.download = `factura_${String(inv.number || 'sin_numero').replace(/\//g, '-')}.pdf`
      document.body.appendChild(a); a.click()
      document.body.removeChild(a); URL.revokeObjectURL(url)
      toast.success(t('invoices.pdf_generated', { number: inv.number }))
    } catch {
      toast.error(t('invoices.error_pdf'))
    } finally {
      setPdfLoadingId(null)
    }
  }
  const { mutate: generatePreview } = useMutation({
    mutationFn: (d: { project_id: string; date_from: string; date_to: string; tax_rate: number }) => invoicesApi.fromTimesheets(d).then(r => r.data),
    onSuccess: (data: PreviewData) => {
      setPreviewData(data)
      setForm(f => ({ ...f, client_name: data.client_name || f.client_name, lines: data.lines || [] }))
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  // Revisión 2026-11: la columna de acciones era `auto` y cada fila es su propia
  // rejilla, así que las filas con y sin botón se desalineaban.
  const COLUMNAS = '150px 80px 1fr 110px 120px 120px 110px 120px 40px'
  const [abierta, setAbierta] = useState<string | null>(null)
  const STATUS_CFG: Record<InvoiceStatus, { label: string; color: string }> = {
    draft: { label: t('invoices.status_draft'), color: 'var(--text-2)' },
    sent: { label: t('invoices.status_sent'), color: 'var(--accent)' },
    paid: { label: t('invoices.status_paid'), color: 'var(--success)' },
    overdue: { label: t('invoices.status_overdue'), color: 'var(--danger)' },
    cancelled: { label: t('invoices.status_cancelled'), color: 'var(--text-3)' }
  }
  const { sort: invSort, setSort: setInvSort, sortedData: sortedInvoices } = useSort(invoices, 'number')

  const compacto = (n?: number) => fmtMoneda(n ?? 0, { moneda: summary?.currency, compacto: true })

  return (
    <div>
      {/* Summary KPIs: en la moneda de la empresa; lo que no tiene tipo de cambio no se suma y se dice. */}
      {summary && Object.keys(summary.sin_tipo_de_cambio ?? {}).length > 0 && (
        <div role="alert" className="invs-box">
          ⚠ {t('invoices.sin_tipo_de_cambio', { monedas: Object.entries(summary.sin_tipo_de_cambio ?? {}).map(([m, v]) => `${v.toLocaleString(localeActivo())} ${m}`).join(', '), base: summary.currency ?? '' })}
        </div>
      )}
      {summary && (
        <div className="invs-grid">
          {[
            {label: t('invoices.total_invoiced'), value: compacto(summary.total_invoiced), color: 'var(--text-1)', icon: '📄'},
            {label: t('invoices.total_paid'), value: compacto(summary.total_paid), color: 'var(--success)', icon: '✓'},
            {label: t('invoices.total_pending'), value: compacto(summary.total_pending), color: 'var(--warning)', icon: '⏳'},
            {label: t('invoices.overdue'), value: compacto(summary.overdue_amount), color: 'var(--danger)', icon: '⚠️'},
            {label: t('invoices.overdue_count'), value: summary.overdue_count||0, color: 'var(--danger)', icon: '📋'},
          ].map(({label,value,color,icon}) => (
            <div key={label} className="invoices-page-e1">
              <div className="invs-box-2">{icon}</div>
              <div className="invs-box-3 invoices-page-e2" style={{ '--invoices-page-color': color } as CSSProperties}>{value}</div>
              <div className="invs-box-4">{label}</div>
            </div>
          ))}
        </div>
      )}

      <Toolbar className="invoices-sx1"
      >
        {/* Mismo reparto que left/right de Toolbar, pero el bloque derecho
            puede partir línea: en un móvil no cabe entero. */}
        <div className="invs-row">
            <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)} className="invoices-page-e3">
              <option value="">{t('invoices.all_projects')}</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </select>
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className={`invoices-page-e4 ${statusFilter ? 'invoices-page-m5' : 'invoices-page-m6'}`}>
              <option value="">{t('invoices.all_statuses')}</option>
              {Object.entries(STATUS_CFG).map(([v,c]) => <option key={v} value={v}>{c.label}</option>)}
            </select>
        </div>
        <div className="invs-row-2">
            <select value={syncProvider} onChange={e => setSyncProvider(e.target.value)}
              className="invs-input">
              <option value="xero">{t('invoices.sync_provider_xero')}</option>
              <option value="quickbooks">{t('invoices.sync_provider_quickbooks')}</option>
            </select>
            <button onClick={() => syncBulk()} disabled={syncing}
              className={`invs-btn ${syncing ? 'invoices-sx2' : 'invoices-sx3'}`}>
              {syncing ? t('invoices.syncing') : t('invoices.sync_bulk')}
            </button>
            {syncStatus && (
              <span className={`u-xs ${ultimaSync ? 'invoices-sx4' : 'invoices-sx5'}`}>
                {ultimaSync
                  ? t('pagina_invs.ultima_sync', { v1: new Date(ultimaSync.replace(' ', 'T')).toLocaleDateString(localeActivo()) })
                  : t('pagina_invs.sin_sincronizar')}
                    {pendientesDeSync > 0 && (
                  <span className="invs-label">({pendientesDeSync}{' '}{t('pagina_invs.pendientes')}</span>
                )}
              </span>
            )}
            <Button onClick={() => setShowCreate(true)}>{t('invoices.new_invoice')}</Button>
        </div>
      </Toolbar>

      {abierta && (
        <FichaDeFactura id={abierta} onClose={() => setAbierta(null)}
          onPdf={() => { const inv = invoices.find(i => String(i.id) === abierta); if (inv) downloadPdf(inv) }}
          onEstado={st => updateStatus({ id: abierta, status: st as InvoiceStatus })}
          etiquetaDeEstado={st => STATUS_CFG[st as InvoiceStatus] || { label: st, color: 'var(--text-2)' }} />
      )}
      {isLoading ? <Spinner /> : invoices.length === 0 ? (
        <EmptyState icon="📄" title={t('invoices.empty_title')} description={t('invoices.empty_description')} />
      ) : (
        <div data-export-table="invoices-list" className="invoices-page-e7">
          <div className="invs-box-5">
          <div className="invs-grid-2 invoices-page-e8" style={{ '--invoices-page-grid-template-columns': COLUMNAS } as CSSProperties}>
            <SortableTH col="number" sort={invSort} onSort={setInvSort}>{t('invoices.number')}</SortableTH>
            <SortableTH col="project_code" sort={invSort} onSort={setInvSort}>{t('invoices.project')}</SortableTH>
            <SortableTH col="client_name" sort={invSort} onSort={setInvSort}>{t('invoices.client')}</SortableTH>
            <SortableTH col="issue_date" sort={invSort} onSort={setInvSort}>{t('invoices.issue_date')}</SortableTH>
            <SortableTH col="due_date" sort={invSort} onSort={setInvSort}>{t('invoices.due_date')}</SortableTH>
            <SortableTH col="total" sort={invSort} onSort={setInvSort}>{t('invoices.total')}</SortableTH>
            <SortableTH col="status" sort={invSort} onSort={setInvSort}>{t('invoices.status')}</SortableTH>
            <span>{t('invoices.actions')}</span>
            <span>{t('invoices.pdf')}</span>
          </div>
          {sortedInvoices.map((inv) => {
            const cfg = STATUS_CFG[(inv.status as InvoiceStatus) || 'draft'] || {label:inv.status || '—',color:'var(--text-2)'}
            const isOverdue = inv.status === 'sent' && inv.due_date && new Date(inv.due_date) < new Date()
            return (
              <div key={inv.id} className="invs-grid-3 invoices-page-e8" style={{ '--invoices-page-grid-template-columns': COLUMNAS } as CSSProperties}>
                <button type="button" onClick={() => setAbierta(String(inv.id))} title={t('invoices.ficha_abrir')} className="invs-btn-2">{inv.number}</button>
                <span className="u-text2-xs">{inv.project_code||'—'}</span>
                <div>
                  <div className="u-base-600">{inv.client_name||'—'}</div>
                  {inv.po_reference && <div className="u-text3-xs">{t('invoices.po', { ref: inv.po_reference })}</div>}
                </div>
                <span className="u-text2-sm">{inv.issue_date}</span>
                <span className={`u-sm ${isOverdue ? 'invoices-sx6' : 'invoices-sx7'}`}>{inv.due_date||'—'}{isOverdue&&' ⚠'}</span>
                <span className="invs-label-2">{fmtMoneda(inv.total||0, { moneda: inv.currency })}</span>
                <span className="invs-label-3 invoices-page-e9" style={{ '--invoices-page-background': alpha(cfg.color, '20'), '--invoices-page-color': cfg.color } as CSSProperties}>{cfg.label}</span>
                <div className="u-row-6">
                  {inv.status === 'draft' && <button onClick={() => updateStatus({id:inv.id,status:'sent'})} className="invs-btn-3">{t('invoices.send')}</button>}
                  {inv.status === 'draft' && <button onClick={() => setAbierta(String(inv.id))} className="invs-btn-4">{t('invoices.ficha_editar')}</button>}
                  {inv.status === 'sent' && <button onClick={() => updateStatus({id:inv.id,status:'paid'})} className="invs-btn-5">{t('invoices.paid')}</button>}
                </div>
                <button onClick={() => downloadPdf(inv)} title={t('invoices.download_pdf')} disabled={pdfLoadingId === inv.id}
                  className={`invs-btn-6 ${pdfLoadingId === inv.id ? 'invoices-sx8' : 'invoices-sx9'}`}>
                  {pdfLoadingId === inv.id ? '⏳' : <Download size={13} />}
                </button>
              </div>
            )
          })}
          </div>
        </div>
      )}

      {showCreate && (
        <Modal open title={t('invoices.new_invoice')} onClose={() => setShowCreate(false)} width={680}>
          <div className="u-stack-14">
            <div className="invs-card">
              <div className="invs-box-6">{t('invoices.generate_from_timesheets')}</div>
              <div className="invs-grid-4">
                <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="invoices-page-e10">{t('invoices.project_label')}</label>
                  <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.project_id} onChange={e => {
                    const proj = projects.find(p => p.id === e.target.value)
                    const client = proj?.client_id ? clients.find(c => c.id === proj.client_id) : null
                    setForm(f => ({...f, project_id: e.target.value,
                      client_id: proj?.client_id ? String(proj.client_id) : f.client_id,
                      client_name: client?.name ?? f.client_name
                    }))
                  }} className="invoices-page-e11">
                    <option value="">{t('invoices.select')}</option>
                    {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
                  </select>
                </div>
                <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="invoices-page-e10">{t('invoices.period_from')}</label><DateInput id={`${idCampo}-2`} value={form.period_from} onChange={e => setForm(f=>({...f,period_from:e.target.value}))} className="invoices-page-e11" /></div>
                <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="invoices-page-e10">{t('invoices.period_to')}</label><DateInput id={`${idCampo}-3`} value={form.period_to} onChange={e => setForm(f=>({...f,period_to:e.target.value}))} className="invoices-page-e11" /></div>
                <Button onClick={() => generatePreview({ project_id: form.project_id, date_from: form.period_from, date_to: form.period_to, tax_rate: form.tax_rate })} disabled={!form.project_id}>
                  {t('invoices.generate_lines')}
                </Button>
              </div>
              {previewData && <div className="invs-box-7">{t('invoices.preview_success', { count: previewData.imputation_count, subtotal: previewData.subtotal, total: previewData.total })}</div>}
            </div>

            <div className="u-grid2-14">
              <div><label className="invoices-page-e10">{t('invoices.client_label')}</label>
                <ClientSelect
                  value={form.client_id}
                  onChange={(id, client) => setForm(f => ({...f, client_id: id, client_name: client ? client.name : ''}))}
                  className="invoices-page-e11"
                />
              </div>
              <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="invoices-page-e10">{t('invoices.client_email')}</label><input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.client_email} onChange={e => setForm(f=>({...f,client_email:e.target.value}))} className="invoices-page-e11" /></div>
              <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="invoices-page-e10">{t('invoices.client_vat')}</label><input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.client_vat} onChange={e => setForm(f=>({...f,client_vat:e.target.value}))} className="invoices-page-e11" /></div>
              <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="invoices-page-e10">{t('invoices.po_reference')}</label><input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.po_reference||''} onChange={e => setForm(f=>({...f,po_reference:e.target.value}))} className="invoices-page-e11" /></div>
              <div><label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="invoices-page-e10">{t('invoices.issue_date_label')}</label><DateInput id={`${idCampo}-7`} value={form.issue_date} onChange={e => setForm(f=>({...f,issue_date:e.target.value}))} className="invoices-page-e11" /></div>
              <div><label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} className="invoices-page-e10">{t('invoices.due_date_label')}</label><DateInput id={`${idCampo}-8`} value={form.due_date} onChange={e => setForm(f=>({...f,due_date:e.target.value}))} className="invoices-page-e11" /></div>
              <div><label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} className="invoices-page-e10">{t('invoices.tax_rate')}</label><input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} type="number" value={form.tax_rate} onChange={e => setForm(f=>({...f,tax_rate:+e.target.value}))} className="invoices-page-e11" /></div>
              <div><label id={`${idCampo}-et10`} htmlFor={`${idCampo}-10`} className="invoices-page-e10">{t('invoices.notes')}</label><input id={`${idCampo}-10`} aria-labelledby={`${idCampo}-et10`} value={form.notes} onChange={e => setForm(f=>({...f,notes:e.target.value}))} className="invoices-page-e11" /></div>
            </div>

            {/* Lines preview */}
            {form.lines.length > 0 && (
              <div className="invs-card-2">
                <div className="invs-box-8">{t('invoices.invoice_lines')}</div>
                {form.lines.map((l,i) => (
                  <div key={i} className="invs-grid-5">
                    <span>{l.description}</span>
                    <span className="invs-label-4">{l.quantity} h</span>
                    <span className="invs-label-4">{fmtMoneda(l.unit_price, { moneda: previewData?.currency||summary?.currency })}/h</span>
                    <span className="invs-label-5">{fmtMoneda(l.amount, { moneda: previewData?.currency||summary?.currency })}</span>
                  </div>
                ))}
              </div>
            )}

            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>{t('invoices.cancel')}</Button>
              <Button onClick={() => create(form)} disabled={isPending || !form.client_id || !form.issue_date}>
                {isPending ? t('invoices.creating') : t('invoices.create_invoice')}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

export default function InvoicesPage(): JSX.Element {
  const t = useAppT()
  return (
    <PageShell>
      <PageHeader icon={<CreditCard size={18} />} title={t('invoices.title')} subtitle={t('invoices.subtitle')} exportTargetSelector='[data-export-table="invoices-list"]' exportFilePrefix='invoices' />
      <InvoicesTab />
    </PageShell>
  )
}
