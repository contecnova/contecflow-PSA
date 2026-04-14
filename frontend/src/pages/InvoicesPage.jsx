/**
 * InvoicesPage — Facturación: crear, gestionar y hacer seguimiento de facturas
 */
import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { projectsApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState, ClientSelect, useSort, SortableTH } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { CreditCard, Download } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

const _PALETTE = ['var(--accent)','var(--success)','var(--warning)','var(--danger)','var(--purple)','var(--warning)']
const fs = { width:'100%', background:'var(--surface-3)', border:'1px solid #1e2d45', borderRadius:8, padding:'9px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }
const card = { background:'var(--surface-2)', border:'1px solid #1e2d45', borderRadius:12 }

// ── Invoices Tab ──────────────────────────────────────────────────────────────
function InvoicesTab() {
  const qc = useQueryClient()

  // ── Sync contable ────────────────────────────────────────────────────────
  const [syncProvider, setSyncProvider] = useState('xero')
  const { mutate: syncBulk, isPending: syncing } = useMutation({
    mutationFn: () => api.post('/accounting/push-invoices-bulk', { provider: syncProvider, limit: 100 }),
    onSuccess: (res) => toast.success(`${res.data.synced} facturas sincronizadas con ${syncProvider}`),
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error de sincronización contable'),
  })
  const toast = useToast()
  const { _invalidate } = useInvalidate()
  const [showCreate, setShowCreate] = useState(false)
  const [selectedProject, setSelectedProject] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [previewData, setPreviewData] = useState(null)
  const [pdfLoadingId, setPdfLoadingId] = useState(null)
  const [form, setForm] = useState({ project_id:'', client_id:'', client_name:'', client_vat:'', client_email:'', issue_date:new Date().toISOString().slice(0,10), due_date:'', tax_rate:21, notes:'', period_from:'', period_to:'', lines:[] })

  const { data: invoices = [], isLoading } = useQuery({
    queryKey: ['invoices', selectedProject, statusFilter],
    queryFn: () => api.get('/invoices', { params: { project_id: selectedProject || undefined, status: statusFilter || undefined } }).then(r => r.data),
  })
  const { data: summary } = useQuery({ queryKey: ['invoice-summary'], queryFn: () => api.get('/invoices/summary').then(r => r.data) })
  const { data: projRaw = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data) })
  const { data: clients = [] } = useQuery({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) })
  const projects = Array.isArray(projRaw) ? projRaw : []

  const { mutate: create, isPending } = useMutation({
    mutationFn: d => api.post('/invoices', d),
    onSuccess: () => { qc.invalidateQueries(['invoices']); qc.invalidateQueries(['invoice-summary']); qc.invalidateQueries(['clients']); qc.invalidateQueries(['client-detail']); qc.invalidateQueries(['client-invoices']); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: updateStatus } = useMutation({
    mutationFn: ({ id, status }) => api.patch(`/invoices/${id}/status`, { status }),
    onSuccess: () => { qc.invalidateQueries(['invoices']); qc.invalidateQueries(['invoice-summary']) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const downloadPdf = async (inv) => {
    setPdfLoadingId(inv.id)
    toast.info(`Generando PDF de ${inv.number}...`)
    try {
      const res = await api.get(`/invoices/${inv.id}/pdf`, { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      const a = document.createElement('a')
      a.href = url
      a.download = `factura_${inv.number.replace(/\//g, '-')}.pdf`
      document.body.appendChild(a); a.click()
      document.body.removeChild(a); URL.revokeObjectURL(url)
      toast.success(`PDF generado: ${inv.number}`)
    } catch {
      toast.error('Error al generar PDF')
    } finally {
      setPdfLoadingId(null)
    }
  }
  const { mutate: generatePreview } = useMutation({
    mutationFn: d => api.post('/invoices/from-timesheets', d).then(r => r.data),
    onSuccess: data => {
      setPreviewData(data)
      setForm(f => ({ ...f, client_name: data.client_name || f.client_name, lines: data.lines }))
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const STATUS_CFG = { draft:{label:'Borrador',color:'var(--text-2)'}, sent:{label:'Enviada',color:'var(--accent)'}, paid:{label:'Pagada',color:'var(--success)'}, overdue:{label:'Vencida',color:'var(--danger)'}, cancelled:{label:'Cancelada',color:'var(--text-3)'} }
  const { sort: invSort, setSort: setInvSort, sortedData: sortedInvoices } = useSort(invoices, 'number')

  return (
    <div>
      {/* Summary KPIs */}
      {summary && (
        <div style={{display:'grid',gridTemplateColumns:'repeat(5,1fr)',gap:12,marginBottom:24}}>
          {[
            {label:'Total facturado',value:`${((summary.total_invoiced||0)/1000).toFixed(0)}K€`,color:'var(--text-1)',icon:'📄'},
            {label:'Cobrado',value:`${((summary.total_paid||0)/1000).toFixed(0)}K€`,color:'var(--success)',icon:'✓'},
            {label:'Pendiente',value:`${((summary.total_pending||0)/1000).toFixed(0)}K€`,color:'var(--warning)',icon:'⏳'},
            {label:'Vencido',value:`${((summary.overdue_amount||0)/1000).toFixed(0)}K€`,color:'var(--danger)',icon:'⚠️'},
            {label:'Facturas vencidas',value:summary.overdue_count||0,color:'var(--danger)',icon:'📋'},
          ].map(({label,value,color,icon}) => (
            <div key={label} style={{...card,padding:'14px 18px'}}>
              <div style={{fontSize:18,marginBottom:6}}>{icon}</div>
              <div style={{fontSize:20,fontWeight:800,color}}>{value}</div>
              <div style={{fontSize:11,color:'var(--text-2)',marginTop:4}}>{label}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{display:'flex',gap:12,marginBottom:20,alignItems:'center'}}>
        <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)} style={{...fs,width:280}}>
          <option value="">Todos los proyectos</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
        </select>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{...fs,width:160,color:statusFilter?'var(--accent)':'var(--text-1)'}}>
          <option value="">Todos los estados</option>
          {Object.entries(STATUS_CFG).map(([v,c]) => <option key={v} value={v}>{c.label}</option>)}
        </select>
        <div style={{marginLeft:'auto'}}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <select value={syncProvider} onChange={e => setSyncProvider(e.target.value)}
              style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8,
                padding: '7px 11px', color: 'var(--text-1)', fontSize: 12, fontFamily: 'var(--font-sans)', outline: 'none' }}>
              <option value="xero">Xero</option>
              <option value="quickbooks">QuickBooks</option>
            </select>
            <button onClick={() => syncBulk()} disabled={syncing}
              style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8,
                padding: '7px 14px', color: syncing ? 'var(--text-3)' : 'var(--success)',
                cursor: syncing ? 'wait' : 'pointer', fontSize: 12, fontFamily: 'var(--font-sans)', fontWeight: 600 }}>
              {syncing ? '⟳ Sincronizando...' : '↑ Sync contable'}
            </button>
            <Button onClick={() => setShowCreate(true)}>+ Nueva factura</Button>
          </div>
        </div>
      </div>

      {isLoading ? <Spinner /> : invoices.length === 0 ? (
        <EmptyState icon="📄" title="Sin facturas" description="Crea tu primera factura o genera una desde las horas imputadas" />
      ) : (
        <div style={{...card,overflow:'hidden'}}>
          <div style={{display:'grid',gridTemplateColumns:'100px 60px 1fr 120px 120px 100px 120px auto 40px',gap:12,padding:'10px 18px',borderBottom:'1px solid #1e2d45',fontSize:10,fontWeight:700,color:'var(--text-2)',textTransform:'uppercase',letterSpacing:'0.07em',alignItems:'center'}}>
            <SortableTH col="number" sort={invSort} onSort={setInvSort}>Nº</SortableTH>
            <SortableTH col="project_code" sort={invSort} onSort={setInvSort}>Proyecto</SortableTH>
            <SortableTH col="client_name" sort={invSort} onSort={setInvSort}>Cliente</SortableTH>
            <SortableTH col="issue_date" sort={invSort} onSort={setInvSort}>Fecha</SortableTH>
            <SortableTH col="due_date" sort={invSort} onSort={setInvSort}>Vencimiento</SortableTH>
            <SortableTH col="total" sort={invSort} onSort={setInvSort}>Total</SortableTH>
            <SortableTH col="status" sort={invSort} onSort={setInvSort}>Estado</SortableTH>
            <span>Acciones</span>
            <span>PDF</span>
          </div>
          {sortedInvoices.map(inv => {
            const cfg = STATUS_CFG[inv.status] || {label:inv.status,color:'var(--text-2)'}
            const isOverdue = inv.status === 'sent' && inv.due_date && new Date(inv.due_date) < new Date()
            return (
              <div key={inv.id} style={{display:'grid',gridTemplateColumns:'100px 60px 1fr 120px 120px 100px 120px auto 40px',gap:12,padding:'12px 18px',borderBottom:'1px solid #1e2d4520',alignItems:'center'}}>
                <span style={{fontSize:12,fontFamily:'monospace',color:'var(--accent)'}}>{inv.number}</span>
                <span style={{fontSize:11,color:'var(--text-2)'}}>{inv.project_code||'—'}</span>
                <div>
                  <div style={{fontSize:13,fontWeight:600}}>{inv.client_name||'—'}</div>
                  {inv.po_reference && <div style={{fontSize:11,color:'var(--text-3)'}}>PO: {inv.po_reference}</div>}
                </div>
                <span style={{fontSize:12,color:'var(--text-2)'}}>{inv.issue_date}</span>
                <span style={{fontSize:12,color:isOverdue?'var(--danger)':'var(--text-2)'}}>{inv.due_date||'—'}{isOverdue&&' ⚠'}</span>
                <span style={{fontSize:13,fontWeight:700,fontFamily:'monospace'}}>{(inv.total||0).toLocaleString('es-ES',{minimumFractionDigits:2})}€</span>
                <span style={{fontSize:11,fontWeight:700,padding:'2px 8px',borderRadius:20,background:cfg.color+'20',color:cfg.color}}>{cfg.label}</span>
                <div style={{display:'flex',gap:6}}>
                  {inv.status === 'draft' && <button onClick={() => updateStatus({id:inv.id,status:'sent'})} style={{background:'var(--accent-muted)',border:'1px solid #00d4ff40',borderRadius:6,padding:'3px 10px',color:'var(--accent)',cursor:'pointer',fontSize:11,fontFamily:'inherit'}}>Enviar</button>}
                  {inv.status === 'sent' && <button onClick={() => updateStatus({id:inv.id,status:'paid'})} style={{background:'var(--success-bg)',border:'1px solid #00e5a040',borderRadius:6,padding:'3px 10px',color:'var(--success)',cursor:'pointer',fontSize:11,fontFamily:'inherit'}}>✓ Pagada</button>}
                </div>
                <button onClick={() => downloadPdf(inv)} title="Descargar PDF" disabled={pdfLoadingId === inv.id}
                  style={{display:'flex',alignItems:'center',justifyContent:'center',background:'none',border:'1px solid #1e2d45',borderRadius:6,width:30,height:26,cursor:pdfLoadingId === inv.id ? 'wait' : 'pointer',color:pdfLoadingId === inv.id ? 'var(--warning)' : 'var(--text-2)'}}>
                  {pdfLoadingId === inv.id ? '⏳' : <Download size={13} />}
                </button>
              </div>
            )
          })}
        </div>
      )}

      {showCreate && (
        <Modal open title="Nueva factura" onClose={() => setShowCreate(false)} width={680}>
          <div style={{display:'flex',flexDirection:'column',gap:14}}>
            <div style={{background:'var(--accent-muted)',border:'1px solid #00d4ff30',borderRadius:8,padding:'12px 16px'}}>
              <div style={{fontSize:12,fontWeight:700,color:'var(--accent)',marginBottom:8}}>Generar desde imputaciones aprobadas</div>
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr auto',gap:10,alignItems:'flex-end'}}>
                <div><label style={ls}>Proyecto</label>
                  <select value={form.project_id} onChange={e => {
                    const proj = projects.find(p => p.id === e.target.value)
                    const client = proj?.client_id ? clients.find(c => c.id === proj.client_id) : null
                    setForm(f => ({...f, project_id: e.target.value,
                      client_id: proj?.client_id || f.client_id,
                      client_name: client ? client.name : f.client_name
                    }))
                  }} style={fs}>
                    <option value="">Seleccionar...</option>
                    {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
                  </select>
                </div>
                <div><label style={ls}>Período desde</label><input type="date" value={form.period_from} onChange={e => setForm(f=>({...f,period_from:e.target.value}))} style={fs} /></div>
                <div><label style={ls}>Período hasta</label><input type="date" value={form.period_to} onChange={e => setForm(f=>({...f,period_to:e.target.value}))} style={fs} /></div>
                <Button onClick={() => generatePreview({ project_id: form.project_id, date_from: form.period_from, date_to: form.period_to, tax_rate: form.tax_rate })} disabled={!form.project_id}>
                  Generar líneas
                </Button>
              </div>
              {previewData && <div style={{marginTop:8,fontSize:12,color:'var(--success)'}}>✓ {previewData.imputation_count} imputaciones · Subtotal: {previewData.subtotal}€ · Total: {previewData.total}€</div>}
            </div>

            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:14}}>
              <div><label style={ls}>Cliente *</label>
                <ClientSelect
                  value={form.client_id}
                  onChange={(id, client) => setForm(f => ({...f, client_id: id, client_name: client ? client.name : ''}))}
                  style={fs}
                />
              </div>
              <div><label style={ls}>Email cliente</label><input value={form.client_email} onChange={e => setForm(f=>({...f,client_email:e.target.value}))} style={fs} /></div>
              <div><label style={ls}>NIF/VAT</label><input value={form.client_vat} onChange={e => setForm(f=>({...f,client_vat:e.target.value}))} style={fs} /></div>
              <div><label style={ls}>Referencia PO</label><input value={form.po_reference||''} onChange={e => setForm(f=>({...f,po_reference:e.target.value}))} style={fs} /></div>
              <div><label style={ls}>Fecha emisión *</label><input type="date" value={form.issue_date} onChange={e => setForm(f=>({...f,issue_date:e.target.value}))} style={fs} /></div>
              <div><label style={ls}>Fecha vencimiento</label><input type="date" value={form.due_date} onChange={e => setForm(f=>({...f,due_date:e.target.value}))} style={fs} /></div>
              <div><label style={ls}>IVA %</label><input type="number" value={form.tax_rate} onChange={e => setForm(f=>({...f,tax_rate:+e.target.value}))} style={fs} /></div>
              <div><label style={ls}>Notas</label><input value={form.notes} onChange={e => setForm(f=>({...f,notes:e.target.value}))} style={fs} /></div>
            </div>

            {/* Lines preview */}
            {form.lines.length > 0 && (
              <div style={{background:'var(--surface-3)',borderRadius:8,padding:12}}>
                <div style={{fontSize:11,fontWeight:700,color:'var(--text-2)',marginBottom:8,textTransform:'uppercase'}}>Líneas de factura</div>
                {form.lines.map((l,i) => (
                  <div key={i} style={{display:'grid',gridTemplateColumns:'1fr 60px 80px 80px',gap:10,padding:'6px 0',borderBottom:'1px solid #1e2d4520',fontSize:12}}>
                    <span>{l.description}</span>
                    <span style={{textAlign:'right',color:'var(--text-2)'}}>{l.quantity} h</span>
                    <span style={{textAlign:'right',color:'var(--text-2)'}}>{l.unit_price}€/h</span>
                    <span style={{textAlign:'right',fontWeight:700}}>{l.amount.toLocaleString('es-ES',{minimumFractionDigits:2})}€</span>
                  </div>
                ))}
              </div>
            )}

            <div style={{display:'flex',justifyContent:'flex-end',gap:10}}>
              <Button variant="secondary" onClick={() => setShowCreate(false)}>Cancelar</Button>
              <Button onClick={() => create(form)} disabled={isPending || !form.client_id || !form.issue_date}>
                {isPending ? 'Creando...' : 'Crear factura'}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

export default function InvoicesPage() {
  const t = useAppT()
  return (
    <div style={{ padding: 32 }}>
      <PageHeader icon={<CreditCard size={18} />} title={t('invoices.title')} subtitle="Facturas, cobros y seguimiento financiero" />
      <InvoicesTab />
    </div>
  )
}
