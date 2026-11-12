/**
 * InvoicesPage — Facturación: crear, gestionar y hacer seguimiento de facturas
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { extractErr, localeActivo } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, invoicesApi, accountingApi, clientsApi, unwrapList } from '../services/api'
import { Button, Modal, Spinner, EmptyState, ClientSelect, useSort, SortableTH, Toolbar } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { CreditCard, Download } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import FichaDeFactura from '../components/invoices/FichaDeFactura'
import { alpha } from '../constants/theme'
import DateInput from '../components/ui/DateInput'

interface InvoiceLine {
  description: string
  quantity: number
  unit_price: number
  amount: number
}

interface InvoiceItem {
  id: string | number
  number?: string
  currency?: string
  project_code?: string
  client_name?: string
  po_reference?: string
  issue_date?: string
  due_date?: string
  total?: number
  status?: string
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

interface SyncStatus {
  last_sync_at?: string
  pending_count?: number
}

interface InvoiceSummary {
  total_invoiced?: number
  total_paid?: number
  total_pending?: number
  overdue_amount?: number
  overdue_count?: number
  currency?: string
  sin_tipo_de_cambio?: Record<string, number>
}

interface PreviewData {
  client_name?: string
  currency?: string
  lines: InvoiceLine[]
  imputation_count?: number
  subtotal?: number
  total?: number
}

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
const fs: CSSProperties = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }
const card: CSSProperties = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12 }

// ── Invoices Tab ──────────────────────────────────────────────────────────────
function InvoicesTab() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()

  // ── Sync contable ────────────────────────────────────────────────────────
  const [syncProvider, setSyncProvider] = useState('xero')
  const { data: syncStatusRaw } = useQuery({
    queryKey: ['accounting-sync-status'],
    queryFn: () => accountingApi.syncStatus().then(r => r.data).catch(() => null),
    staleTime: 60_000,
  })
  const syncStatus = (syncStatusRaw ?? null) as SyncStatus | null
  const { mutate: syncBulk, isPending: syncing } = useMutation({
    mutationFn: () => accountingApi.pushBulk({ provider: syncProvider, limit: 100 }),
    onSuccess: (res: { data?: { synced?: number } }) => toast.success(t('invoices.sync_success', { count: res.data?.synced || 0, provider: syncProvider })),
    onError: (e: unknown) => toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || t('invoices.sync_error')),
  })
  const [showCreate, setShowCreate] = useState(false)
  const [selectedProject, setSelectedProject] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [previewData, setPreviewData] = useState<PreviewData | null>(null)
  const [pdfLoadingId, setPdfLoadingId] = useState<string | number | null>(null)
  const [form, setForm] = useState<InvoiceCreateForm>({ project_id:'', client_id:'', client_name:'', client_vat:'', client_email:'', issue_date:new Date().toISOString().slice(0,10), due_date:'', tax_rate:21, notes:'', period_from:'', period_to:'', po_reference:'', lines:[] })

  const { data: invoicesRaw = [], isLoading } = useQuery({
    queryKey: ['invoices', selectedProject, statusFilter],
    queryFn: () => invoicesApi.list({ project_id: selectedProject || undefined, status: statusFilter || undefined }).then(r => r.data),
  })
  const invoices = invoicesRaw as InvoiceItem[]
  const { data: summaryRaw } = useQuery({ queryKey: ['invoice-summary'], queryFn: () => invoicesApi.summary().then(r => r.data) })
  const summary = (summaryRaw ?? null) as InvoiceSummary | null
  const { data: projectsRaw = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list({}).then(unwrapList) })
  const projects = projectsRaw as ProjectItem[]
  const { data: clientsRaw = [] } = useQuery({ queryKey: ['clients'], queryFn: () => clientsApi.list({ page_size: 200 }).then(unwrapList) })
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

  const downloadPdf = async (inv: InvoiceItem) => {
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
  const { sort: invSort, setSort: setInvSort, sortedData: sortedInvoicesRaw } = useSort(invoices as unknown as Record<string, unknown>[], 'number')
  const sortedInvoices = sortedInvoicesRaw as unknown as InvoiceItem[]

  const compacto = (n?: number) => (n ?? 0).toLocaleString(localeActivo(), { style: 'currency', currency: summary?.currency || 'EUR', notation: 'compact', maximumFractionDigits: 1 })

  return (
    <div>
      {/* Summary KPIs: en la moneda de la empresa; lo que no tiene tipo de cambio no se suma y se dice. */}
      {summary && Object.keys(summary.sin_tipo_de_cambio ?? {}).length > 0 && (
        <div role="alert" style={{ marginBottom: 10, fontSize: 'var(--text-sm)', color: 'var(--warning)' }}>
          ⚠ {t('invoices.sin_tipo_de_cambio', { monedas: Object.entries(summary.sin_tipo_de_cambio ?? {}).map(([m, v]) => `${v.toLocaleString(localeActivo())} ${m}`).join(', '), base: summary.currency ?? '' })}
        </div>
      )}
      {summary && (
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit, minmax(min(150px, 100%), 1fr))',gap:12,marginBottom:24}}>
          {[
            {label: t('invoices.total_invoiced'), value: compacto(summary.total_invoiced), color: 'var(--text-1)', icon: '📄'},
            {label: t('invoices.total_paid'), value: compacto(summary.total_paid), color: 'var(--success)', icon: '✓'},
            {label: t('invoices.total_pending'), value: compacto(summary.total_pending), color: 'var(--warning)', icon: '⏳'},
            {label: t('invoices.overdue'), value: compacto(summary.overdue_amount), color: 'var(--danger)', icon: '⚠️'},
            {label: t('invoices.overdue_count'), value: summary.overdue_count||0, color: 'var(--danger)', icon: '📋'},
          ].map(({label,value,color,icon}) => (
            <div key={label} style={{...card,padding:'14px 18px'}}>
              <div style={{fontSize: "var(--text-lg-em)",marginBottom:6}}>{icon}</div>
              <div style={{fontSize: "var(--text-xl)",fontWeight:800,color}}>{value}</div>
              <div style={{fontSize: "var(--text-xs)",color:'var(--text-2)',marginTop:4}}>{label}</div>
            </div>
          ))}
        </div>
      )}

      <Toolbar
        style={{ marginBottom: 20 }}
      >
        {/* Mismo reparto que left/right de Toolbar, pero el bloque derecho
            puede partir línea: en un móvil no cabe entero. */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', flex: 1, minWidth: 0 }}>
            <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)} style={{...fs,width:280,flex:'2 1 240px',minWidth:0,maxWidth:'100%'}}>
              <option value="">{t('invoices.all_projects')}</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </select>
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{...fs,width:160,flex:'1 1 160px',minWidth:0,maxWidth:'100%',color:statusFilter?'var(--accent)':'var(--text-1)'}}>
              <option value="">{t('invoices.all_statuses')}</option>
              {Object.entries(STATUS_CFG).map(([v,c]) => <option key={v} value={v}>{c.label}</option>)}
            </select>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', maxWidth: '100%', marginLeft: 'auto' }}>
            <select value={syncProvider} onChange={e => setSyncProvider(e.target.value)}
              style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8,
                padding: '7px 11px', color: 'var(--text-1)', fontSize: "var(--text-sm)", fontFamily: 'var(--font-sans)', outline: 'none' }}>
              <option value="xero">{t('invoices.sync_provider_xero')}</option>
              <option value="quickbooks">{t('invoices.sync_provider_quickbooks')}</option>
            </select>
            <button onClick={() => syncBulk()} disabled={syncing}
              style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8,
                padding: '7px 14px', color: syncing ? 'var(--text-3)' : 'var(--success)',
                cursor: syncing ? 'wait' : 'pointer', fontSize: "var(--text-sm)", fontFamily: 'var(--font-sans)', fontWeight: 600 }}>
              {syncing ? t('invoices.syncing') : t('invoices.sync_bulk')}
            </button>
            {syncStatus && (
              <span style={{ fontSize: "var(--text-xs)", color: syncStatus.last_sync_at ? 'var(--text-3)' : 'var(--warning)' }}>
                {syncStatus.last_sync_at
                  ? `Última sync: ${new Date(syncStatus.last_sync_at).toLocaleDateString(localeActivo())}`
                  : 'Sin sincronizar'}
                    {(syncStatus.pending_count || 0) > 0 && (
                  <span style={{ marginLeft: 6, color: 'var(--warning)', fontWeight: 600 }}>({syncStatus.pending_count} pendientes)</span>
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
        <div data-export-table="invoices-list" style={{...card,overflowX:'auto'}}>
          <div style={{minWidth:1000}}>
          <div style={{display:'grid',gridTemplateColumns:COLUMNAS,gap:12,padding:'10px 18px',borderBottom:'1px solid var(--surface-4)',fontSize: "var(--text-2xs)",fontWeight:700,color:'var(--text-2)',textTransform:'uppercase',letterSpacing:'0.07em',alignItems:'center'}}>
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
              <div key={inv.id} style={{display:'grid',gridTemplateColumns:COLUMNAS,gap:12,padding:'12px 18px',borderBottom:'1px solid color-mix(in srgb, var(--surface-4) 13%, transparent)',alignItems:'center'}}>
                <button type="button" onClick={() => setAbierta(String(inv.id))} title={t('invoices.ficha_abrir')} style={{fontSize: "var(--text-sm)",fontFamily:'var(--font-mono)',color:'var(--accent)',background:'none',border:'none',padding:0,cursor:'pointer',textAlign:'left',textDecoration:'underline',textUnderlineOffset:3}}>{inv.number}</button>
                <span className="u-text2-xs">{inv.project_code||'—'}</span>
                <div>
                  <div className="u-base-600">{inv.client_name||'—'}</div>
                  {inv.po_reference && <div className="u-text3-xs">{t('invoices.po', { ref: inv.po_reference })}</div>}
                </div>
                <span className="u-text2-sm">{inv.issue_date}</span>
                <span style={{fontSize: "var(--text-sm)",color:isOverdue?'var(--danger)':'var(--text-2)'}}>{inv.due_date||'—'}{isOverdue&&' ⚠'}</span>
                <span style={{fontSize: "var(--text-base)",fontWeight:700,fontFamily:'var(--font-mono)'}}>{(inv.total||0).toLocaleString(localeActivo(),{style:'currency',currency:inv.currency||'EUR'})}</span>
                <span style={{fontSize: "var(--text-xs)",fontWeight:700,padding:'2px 8px',borderRadius:20,background:alpha(cfg.color, '20'),color:cfg.color}}>{cfg.label}</span>
                <div className="u-row-6">
                  {inv.status === 'draft' && <button onClick={() => updateStatus({id:inv.id,status:'sent'})} style={{background:'var(--accent-muted)',border:'1px solid var(--accent-border-strong)',borderRadius:6,padding:'3px 10px',color:'var(--accent)',cursor:'pointer',fontSize: "var(--text-xs)",fontFamily:'inherit'}}>{t('invoices.send')}</button>}
                  {inv.status === 'draft' && <button onClick={() => setAbierta(String(inv.id))} style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'3px 10px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-xs)",fontFamily:'inherit'}}>{t('invoices.ficha_editar')}</button>}
                  {inv.status === 'sent' && <button onClick={() => updateStatus({id:inv.id,status:'paid'})} style={{background:'var(--success-bg)',border:'1px solid var(--success-border)',borderRadius:6,padding:'3px 10px',color:'var(--success)',cursor:'pointer',fontSize: "var(--text-xs)",fontFamily:'inherit'}}>{t('invoices.paid')}</button>}
                </div>
                <button onClick={() => downloadPdf(inv)} title={t('invoices.download_pdf')} disabled={pdfLoadingId === inv.id}
                  style={{display:'flex',alignItems:'center',justifyContent:'center',background:'none',border:'1px solid var(--surface-4)',borderRadius:6,width:30,height:26,cursor:pdfLoadingId === inv.id ? 'wait' : 'pointer',color:pdfLoadingId === inv.id ? 'var(--warning)' : 'var(--text-2)'}}>
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
            <div style={{background:'var(--accent-muted)',border:'1px solid var(--accent-border)',borderRadius:8,padding:'12px 16px'}}>
              <div style={{fontSize: "var(--text-sm)",fontWeight:700,color:'var(--accent)',marginBottom:8}}>{t('invoices.generate_from_timesheets')}</div>
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr auto',gap:10,alignItems:'flex-end'}}>
                <div><label style={ls}>{t('invoices.project_label')}</label>
                  <select value={form.project_id} onChange={e => {
                    const proj = projects.find(p => p.id === e.target.value)
                    const client = proj?.client_id ? clients.find(c => c.id === proj.client_id) : null
                    setForm(f => ({...f, project_id: e.target.value,
                      client_id: proj?.client_id ? String(proj.client_id) : f.client_id,
                      client_name: client?.name ?? f.client_name
                    }))
                  }} style={fs}>
                    <option value="">{t('invoices.select')}</option>
                    {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
                  </select>
                </div>
                <div><label style={ls}>{t('invoices.period_from')}</label><DateInput value={form.period_from} onChange={e => setForm(f=>({...f,period_from:e.target.value}))} style={fs} /></div>
                <div><label style={ls}>{t('invoices.period_to')}</label><DateInput value={form.period_to} onChange={e => setForm(f=>({...f,period_to:e.target.value}))} style={fs} /></div>
                <Button onClick={() => generatePreview({ project_id: form.project_id, date_from: form.period_from, date_to: form.period_to, tax_rate: form.tax_rate })} disabled={!form.project_id}>
                  {t('invoices.generate_lines')}
                </Button>
              </div>
              {previewData && <div style={{marginTop:8,fontSize: "var(--text-sm)",color:'var(--success)'}}>{t('invoices.preview_success', { count: previewData.imputation_count, subtotal: previewData.subtotal, total: previewData.total })}</div>}
            </div>

            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:14}}>
              <div><label style={ls}>{t('invoices.client_label')}</label>
                <ClientSelect
                  value={form.client_id}
                  onChange={(id, client) => setForm(f => ({...f, client_id: id, client_name: client ? client.name : ''}))}
                  style={fs}
                />
              </div>
              <div><label style={ls}>{t('invoices.client_email')}</label><input value={form.client_email} onChange={e => setForm(f=>({...f,client_email:e.target.value}))} style={fs} /></div>
              <div><label style={ls}>{t('invoices.client_vat')}</label><input value={form.client_vat} onChange={e => setForm(f=>({...f,client_vat:e.target.value}))} style={fs} /></div>
              <div><label style={ls}>{t('invoices.po_reference')}</label><input value={form.po_reference||''} onChange={e => setForm(f=>({...f,po_reference:e.target.value}))} style={fs} /></div>
              <div><label style={ls}>{t('invoices.issue_date_label')}</label><DateInput value={form.issue_date} onChange={e => setForm(f=>({...f,issue_date:e.target.value}))} style={fs} /></div>
              <div><label style={ls}>{t('invoices.due_date_label')}</label><DateInput value={form.due_date} onChange={e => setForm(f=>({...f,due_date:e.target.value}))} style={fs} /></div>
              <div><label style={ls}>{t('invoices.tax_rate')}</label><input type="number" value={form.tax_rate} onChange={e => setForm(f=>({...f,tax_rate:+e.target.value}))} style={fs} /></div>
              <div><label style={ls}>{t('invoices.notes')}</label><input value={form.notes} onChange={e => setForm(f=>({...f,notes:e.target.value}))} style={fs} /></div>
            </div>

            {/* Lines preview */}
            {form.lines.length > 0 && (
              <div style={{background:'var(--surface-3)',borderRadius:8,padding:12}}>
                <div style={{fontSize: "var(--text-xs)",fontWeight:700,color:'var(--text-2)',marginBottom:8,textTransform:'uppercase'}}>{t('invoices.invoice_lines')}</div>
                {form.lines.map((l,i) => (
                  <div key={i} style={{display:'grid',gridTemplateColumns:'1fr 60px 80px 80px',gap:10,padding:'6px 0',borderBottom:'1px solid color-mix(in srgb, var(--surface-4) 13%, transparent)',fontSize: "var(--text-sm)"}}>
                    <span>{l.description}</span>
                    <span style={{textAlign:'right',color:'var(--text-2)'}}>{l.quantity} h</span>
                    <span style={{textAlign:'right',color:'var(--text-2)'}}>{l.unit_price.toLocaleString(localeActivo(),{style:'currency',currency:previewData?.currency||summary?.currency||'EUR'})}/h</span>
                    <span style={{textAlign:'right',fontWeight:700}}>{l.amount.toLocaleString(localeActivo(),{style:'currency',currency:previewData?.currency||summary?.currency||'EUR'})}</span>
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
