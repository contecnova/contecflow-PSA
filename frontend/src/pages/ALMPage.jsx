import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { fmtCurrency, fmtDate, extractErr} from '../utils/helpers'
import { sanitizeUrl } from '../utils/security'
import { useAppT } from '../i18n/AppLangContext'

// ── Constantes ────────────────────────────────────────────────────────────────
const VENDOR_CATS = {
  software:   { label: 'Software',    icon: '💻', color: 'var(--accent)' },
  hardware:   { label: 'Hardware',    icon: '🖥️', color: 'var(--purple)' },
  saas:       { label: 'SaaS',        icon: '☁️', color: 'var(--success)' },
  cloud:      { label: 'Cloud',       icon: '⛅', color: 'var(--accent)' },
  telecom:    { label: 'Telecom',     icon: '📡', color: 'var(--warning)' },
  consulting: { label: 'Consultoría', icon: '🏢', color: 'var(--purple)' },
  other:      { label: 'Otro',        icon: '📦', color: 'var(--text-2)' },
}

const CONTRACT_TYPES = {
  purchase:     { label: 'Compra',         icon: '🛒' },
  subscription: { label: 'Suscripción',    icon: '🔄' },
  maintenance:  { label: 'Mantenimiento',  icon: '🔧' },
  support:      { label: 'Soporte',        icon: '🎫' },
  lease:        { label: 'Arrendamiento',  icon: '📋' },
  enterprise:   { label: 'Enterprise',     icon: '🏛️' },
}

const CONTRACT_STATUS = {
  active:    { label: 'Activo',    color: 'var(--success)' },
  expired:   { label: 'Expirado', color: 'var(--danger)' },
  cancelled: { label: 'Cancelado',color: 'var(--text-2)' },
  pending:   { label: 'Pendiente',color: 'var(--warning)' },
  draft:     { label: 'Borrador', color: 'var(--text-3)' },
}

const LICENSE_TYPES = {
  perpetual:    { label: 'Perpetua',      icon: '♾️' },
  subscription: { label: 'Suscripción',   icon: '🔄' },
  concurrent:   { label: 'Concurrente',   icon: '👥' },
  named:        { label: 'Nominal',       icon: '👤' },
  device:       { label: 'Por dispositivo',icon: '🖥️' },
  trial:        { label: 'Trial',         icon: '⏱️' },
  free:         { label: 'Gratuita',      icon: '🆓' },
  oem:          { label: 'OEM',           icon: '🔩' },
  volume:       { label: 'Volumen',       icon: '📦' },
}

const LICENSE_STATUS_CFG = {
  active:        { label: 'Activa',          color: 'var(--success)' },
  expired:       { label: 'Expirada',        color: 'var(--danger)' },
  unassigned:    { label: 'Sin asignar',     color: 'var(--text-2)' },
  overallocated: { label: 'Sobreasignada',   color: 'var(--danger)' },
  cancelled:     { label: 'Cancelada',       color: 'var(--text-3)' },
}

const ASSET_TYPES = {
  laptop:     { label: 'Portátil',     icon: '💻' },
  desktop:    { label: 'Escritorio',   icon: '🖥️' },
  server:     { label: 'Servidor',     icon: '🗄️' },
  mobile:     { label: 'Móvil',        icon: '📱' },
  tablet:     { label: 'Tablet',       icon: '📟' },
  network:    { label: 'Red',          icon: '🌐' },
  printer:    { label: 'Impresora',    icon: '🖨️' },
  monitor:    { label: 'Monitor',      icon: '🖥' },
  peripheral: { label: 'Periférico',   icon: '🖱️' },
  vm:         { label: 'Máquina Virtual',icon: '☁️' },
  other:      { label: 'Otro',         icon: '📦' },
}

const ASSET_STATUS_CFG = {
  in_use:    { label: 'En uso',         color: 'var(--accent)' },
  available: { label: 'Disponible',     color: 'var(--success)' },
  in_repair: { label: 'En reparación',  color: 'var(--warning)' },
  retired:   { label: 'Retirado',       color: 'var(--text-2)' },
  lost:      { label: 'Perdido',        color: 'var(--danger)' },
  stolen:    { label: 'Robado',         color: 'var(--danger)' },
}

// ── Estilos compartidos ───────────────────────────────────────────────────────
const card  = { background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12 }
const fs    = { background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', width: '100%' }
const ls    = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 6 }

const StatusBadge = ({ status, cfg }) => {
  const c = cfg[status] || { label: status, color: 'var(--text-2)' }
  return (
    <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 9px', borderRadius: 20,
      background: c.color + '20', color: c.color, border: `1px solid ${c.color}40` }}>
      {c.label}
    </span>
  )
}

const KPI = ({ icon, label, value, sub, color = 'var(--accent)', alert }) => (
  <div style={{ ...card, padding: '20px 22px', display: 'flex', gap: 14, alignItems: 'center',
    ...(alert ? { borderColor: 'var(--danger-border)', background: 'var(--danger-bg)' } : {}) }}>
    <div style={{ fontSize: 28, flexShrink: 0 }}>{icon}</div>
    <div>
      <div style={{ fontSize: 24, fontWeight: 800, color, lineHeight: 1.1 }}>{value}</div>
      <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2 }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>{sub}</div>}
    </div>
  </div>
)

const SectionTitle = ({ children, action }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
    <h3 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>{children}</h3>
    {action}
  </div>
)


// ── Dashboard ALM ─────────────────────────────────────────────────────────────
function ALMDashboard({ onNavigate }) {
  const { data: dash = {}, isLoading } = useQuery({
    queryKey: ['alm-dashboard'],
    queryFn: () => api.get('/alm/dashboard').then(r => r.data),
    refetchInterval: 60000,
  })
  const kpis = dash.kpis || {}
  const renewals = dash.upcoming_renewals || []

  if (isLoading) return <div style={{ padding: 40, textAlign: 'center' }}><Spinner size={32} /></div>

  return (
    <div>
      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 14, marginBottom: 28 }}>
        <KPI icon="📄" label="Contratos activos"        value={kpis.total_contracts ?? 0}   color="#00d4ff"
          sub={kpis.expiring_soon ? `${kpis.expiring_soon} expiran en 60 días` : undefined}
          alert={kpis.expiring_soon > 0} />
        <KPI icon="🔑" label="Licencias gestionadas"   value={kpis.total_licenses ?? 0}    color="#7c3aed"
          sub={kpis.expired_licenses ? `${kpis.expired_licenses} expiradas` : undefined}
          alert={kpis.expired_licenses > 0} />
        <KPI icon="🖥️" label="Activos inventariados"  value={kpis.total_assets ?? 0}       color="#00e5a0"
          sub={`${kpis.assets_in_use ?? 0} en uso`} />
        <KPI icon="🏢" label="Proveedores activos"     value={kpis.total_vendors ?? 0}      color="#f97316" />
        <KPI icon="💰" label="Coste anual licencias"   value={fmtCurrency(kpis.annual_license_cost ?? 0)} color="#ffb800" sub="licencias activas" />
        <KPI icon="📊" label="Coste anual total"       value={fmtCurrency(kpis.total_annual_cost ?? 0)}   color="#ff4757" sub="contratos + licencias" />
      </div>

      {/* Renovaciones próximas */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <div style={card}>
          <div style={{ padding: '18px 20px 14px' }}>
            <SectionTitle>⚠️ Renovaciones próximas (60 días)
              <Button onClick={() => onNavigate('contracts')} variant="secondary">Ver contratos →</Button>
            </SectionTitle>
            {renewals.length === 0 ? (
              <div style={{ padding: '20px 0', textAlign: 'center', color: 'var(--text-2)', fontSize: 13 }}>
                ✅ Sin renovaciones urgentes
              </div>
            ) : (
              renewals.map(c => (
                <div key={c.id} style={{ padding: '10px 0', borderBottom: '1px solid #1e2d4530', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{c.title}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{c.vendor_name}</div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0, marginLeft: 12 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: c.days_to_renewal <= 14 ? 'var(--danger)' : c.days_to_renewal <= 30 ? 'var(--warning)' : 'var(--success)' }}>
                      {c.days_to_renewal === 0 ? 'Hoy' : `${c.days_to_renewal}d`}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{fmtDate(c.renewal_date)}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div style={card}>
          <div style={{ padding: '18px 20px 14px' }}>
            <SectionTitle>💡 Acciones rápidas</SectionTitle>
            {[
              { icon: '🏢', label: 'Añadir proveedor',   tab: 'vendors',   color: 'var(--accent)' },
              { icon: '📄', label: 'Nuevo contrato',      tab: 'contracts', color: 'var(--purple)' },
              { icon: '🔑', label: 'Registrar licencia',  tab: 'licenses',  color: 'var(--success)' },
              { icon: '🖥️', label: 'Añadir activo',      tab: 'assets',    color: 'var(--warning)' },
              { icon: '💼', label: 'Centros de coste',    tab: 'cost',      color: 'var(--warning)' },
              { icon: '📊', label: 'Informe compliance',  tab: 'compliance',color: 'var(--danger)' },
            ].map(a => (
              <button key={a.tab} onClick={() => onNavigate(a.tab)}
                style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 8, border: '1px solid #1e2d45', background: 'transparent', color: 'var(--text-1)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit', marginBottom: 6, textAlign: 'left', transition: 'border-color 0.15s' }}
                onMouseEnter={e => e.currentTarget.style.borderColor = a.color + '60'}
                onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}>
                <span style={{ fontSize: 16 }}>{a.icon}</span>
                {a.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Vendors ────────────────────────────────────────────────────────────────────
function VendorModal({ vendor, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!vendor
  const [form, setForm] = useState({
    name: vendor?.name || '', category: vendor?.category || 'software',
    website: vendor?.website || '', support_email: vendor?.support_email || '',
    support_phone: vendor?.support_phone || '', account_manager: vendor?.account_manager || '',
    account_number: vendor?.account_number || '', tax_id: vendor?.tax_id || '',
    country: vendor?.country || 'ES', notes: vendor?.notes || '',
  })
  const s = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit ? api.patch(`/alm/vendors/${vendor.id}`, d) : api.post('/alm/vendors', d),
    onSuccess: () => { qc.invalidateQueries(['alm-vendors']); qc.invalidateQueries(['alm-dashboard']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar proveedor' : 'Nuevo proveedor'} width={640}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}><label style={ls}>Nombre *</label><input value={form.name} onChange={s('name')} style={fs} placeholder="Microsoft, AWS, GitHub..." /></div>
        <div>
          <label style={ls}>Categoría</label>
          <select value={form.category} onChange={s('category')} style={fs}>
            {Object.entries(VENDOR_CATS).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
          </select>
        </div>
        <div><label style={ls}>País</label><input value={form.country} onChange={s('country')} style={fs} placeholder="ES" /></div>
        <div><label style={ls}>Web</label><input value={form.website} onChange={s('website')} style={fs} placeholder="https://..." /></div>
        <div><label style={ls}>Email soporte</label><input value={form.support_email} onChange={s('support_email')} style={fs} /></div>
        <div><label style={ls}>Teléfono soporte</label><input value={form.support_phone} onChange={s('support_phone')} style={fs} /></div>
        <div><label style={ls}>Account Manager</label><input value={form.account_manager} onChange={s('account_manager')} style={fs} /></div>
        <div><label style={ls}>Nº cliente</label><input value={form.account_number} onChange={s('account_number')} style={fs} /></div>
        <div><label style={ls}>CIF/NIF</label><input value={form.tax_id} onChange={s('tax_id')} style={fs} /></div>
        <div style={{ gridColumn: '1/-1' }}><label style={ls}>Notas</label><textarea value={form.notes} onChange={s('notes')} rows={3} style={{ ...fs, resize: 'vertical' }} /></div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
        <Button variant="secondary" onClick={onClose}>Cancelar</Button>
        <Button onClick={() => mutate(form)} disabled={isPending || !form.name} loading={isPending}>
          {isPending ? 'Guardando...' : isEdit ? 'Guardar' : 'Crear proveedor'}
        </Button>
      </div>
    </Modal>
  )
}

function VendorsTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const [modal, setModal] = useState(null)
  const [search, setSearch] = useState('')
  const [catFilter, setCatFilter] = useState('')

  const { data: vendors = [], isLoading } = useQuery({
    queryKey: ['alm-vendors'],
    queryFn: () => api.get('/alm/vendors').then(r => r.data),
  })
  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/alm/vendors/${id}`),
    onSuccess: () => qc.invalidateQueries(['alm-vendors']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const filtered = vendors.filter(v =>
    (!search || v.name.toLowerCase().includes(search.toLowerCase())) &&
    (!catFilter || v.category === catFilter)
  )

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar proveedor..."
          style={{ ...fs, flex: 2 }} />
        <select value={catFilter} onChange={e => setCatFilter(e.target.value)} style={{ ...fs, flex: 1 }}>
          <option value="">Todas las categorías</option>
          {Object.entries(VENDOR_CATS).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
        </select>
        <Button onClick={() => setModal({})} icon="＋">Nuevo proveedor</Button>
      </div>

      {isLoading ? <Spinner /> : filtered.length === 0 ? (
        <EmptyState icon="🏢" title="Sin proveedores" description="Añade los proveedores de software, hardware y servicios de tu empresa" />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 }}>
          {filtered.map(v => {
            const cat = VENDOR_CATS[v.category] || VENDOR_CATS.other
            return (
              <div key={v.id} style={{ ...card, padding: '18px 20px', transition: 'border-color 0.15s' }}
                onMouseEnter={e => e.currentTarget.style.borderColor = cat.color + '50'}
                onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 36, height: 36, borderRadius: 9, background: cat.color + '20', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>
                      {cat.icon}
                    </div>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700 }}>{v.name}</div>
                      <div style={{ fontSize: 11, color: cat.color, fontWeight: 600 }}>{cat.label}</div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button onClick={() => setModal(v)} style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12 }}>✏️</button>
                    <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar proveedor "${v.name}"?`, onConfirm: () => del(v.id), danger: true }) }}
                      style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '4px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: 12 }}>🗑</button>
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--text-2)' }}>
                  {v.account_manager && <span>👤 {v.account_manager}</span>}
                  {v.support_email   && <span>✉️ {v.support_email}</span>}
                  {v.website         && <a href={sanitizeUrl(v.website)} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', fontSize: 12 }}>🔗 {v.website}</a>}
                </div>
                <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid #1e2d4530', fontSize: 11, color: 'var(--text-3)' }}>
                  {v.contracts_count} contrato(s)
                </div>
              </div>
            )
          })}
        </div>
      )}
      {modal !== null && <VendorModal vendor={Object.keys(modal).length ? modal : null} onClose={() => setModal(null)} />}
    </div>
  )
}

// ── Contracts ─────────────────────────────────────────────────────────────────
function ContractModal({ contract, vendors, users, costCenters, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const isEdit = !!contract?.id
  const today = new Date().toISOString().slice(0, 10)
  const [form, setForm] = useState({
    title: contract?.title || '',
    vendor_id: contract?.vendor_id || '',
    type: contract?.type || 'subscription',
    status: contract?.status || 'active',
    start_date: contract?.start_date || today,
    end_date: contract?.end_date || '',
    renewal_date: contract?.renewal_date || '',
    auto_renew: contract?.auto_renew ?? false,
    notice_days: contract?.notice_days ?? 30,
    total_value: contract?.total_value || '',
    annual_value: contract?.annual_value || '',
    billing_cycle: contract?.billing_cycle || 'annual',
    currency: contract?.currency || 'EUR',
    payment_method: contract?.payment_method || '',
    po_number: contract?.po_number || '',
    cost_center_id: contract?.cost_center_id || '',
    owner_id: contract?.owner_id || '',
    document_url: contract?.document_url || '',
    notes: contract?.notes || '',
    tags: contract?.tags || '',
  })
  const s = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit ? api.patch(`/alm/contracts/${contract.id}`, d) : api.post('/alm/contracts', d),
    onSuccess: () => { qc.invalidateQueries(['alm-contracts']); qc.invalidateQueries(['alm-dashboard']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar contrato' : 'Nuevo contrato'} width={720}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}><label style={ls}>Título *</label><input value={form.title} onChange={s('title')} style={fs} placeholder="Microsoft 365 Business Premium — 2025" /></div>
        <div>
          <label style={ls}>Proveedor</label>
          <select value={form.vendor_id} onChange={s('vendor_id')} style={fs}>
            <option value="">Sin proveedor</option>
            {vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Tipo</label>
          <select value={form.type} onChange={s('type')} style={fs}>
            {Object.entries(CONTRACT_TYPES).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Estado</label>
          <select value={form.status} onChange={s('status')} style={fs}>
            {Object.entries(CONTRACT_STATUS).map(([k,v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Ciclo facturación</label>
          <select value={form.billing_cycle} onChange={s('billing_cycle')} style={fs}>
            {[['one_time','Único'],['monthly','Mensual'],['quarterly','Trimestral'],['annual','Anual'],['biennial','Bienal']].map(([k,l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
        <div><label style={ls}>Fecha inicio</label><input type="date" value={form.start_date} onChange={s('start_date')} style={fs} /></div>
        <div><label style={ls}>Fecha fin</label><input type="date" value={form.end_date} onChange={s('end_date')} style={fs} /></div>
        <div><label style={ls}>Fecha renovación</label><input type="date" value={form.renewal_date} onChange={s('renewal_date')} style={fs} /></div>
        <div>
          <label style={ls}>Renovación automática</label>
          <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
            {[true, false].map(v => (
              <button key={String(v)} onClick={() => setForm(f => ({ ...f, auto_renew: v }))}
                style={{ flex: 1, padding: '8px', borderRadius: 8, border: `1px solid ${form.auto_renew === v ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: form.auto_renew === v ? 'var(--accent-muted)' : 'transparent', color: form.auto_renew === v ? 'var(--accent)' : 'var(--text-2)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>
                {v ? '✅ Sí' : '❌ No'}
              </button>
            ))}
          </div>
        </div>
        <div><label style={ls}>Días preaviso cancelación</label><input type="number" value={form.notice_days} onChange={s('notice_days')} style={fs} /></div>
        <div><label style={ls}>Valor total (€)</label><input type="number" value={form.total_value} onChange={s('total_value')} style={fs} /></div>
        <div><label style={ls}>Coste anual (€)</label><input type="number" value={form.annual_value} onChange={s('annual_value')} style={fs} /></div>
        <div>
          <label style={ls}>Responsable</label>
          <select value={form.owner_id} onChange={s('owner_id')} style={fs}>
            <option value="">Sin responsable</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Centro de coste</label>
          <select value={form.cost_center_id} onChange={s('cost_center_id')} style={fs}>
            <option value="">Sin centro de coste</option>
            {costCenters.map(c => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
          </select>
        </div>
        <div><label style={ls}>Nº pedido (PO)</label><input value={form.po_number} onChange={s('po_number')} style={fs} /></div>
        <div><label style={ls}>Método de pago</label><input value={form.payment_method} onChange={s('payment_method')} style={fs} placeholder="Tarjeta, transferencia..." /></div>
        <div style={{ gridColumn: '1/-1' }}><label style={ls}>URL documento</label><input value={form.document_url} onChange={s('document_url')} style={fs} placeholder="https://drive.google.com/..." /></div>
        <div style={{ gridColumn: '1/-1' }}><label style={ls}>Notas</label><textarea value={form.notes} onChange={s('notes')} rows={3} style={{ ...fs, resize: 'vertical' }} /></div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
        <Button variant="secondary" onClick={onClose}>Cancelar</Button>
        <Button onClick={() => mutate(form)} disabled={isPending || !form.title} loading={isPending}>
          {isPending ? 'Guardando...' : isEdit ? 'Guardar cambios' : 'Crear contrato'}
        </Button>
      </div>
    </Modal>
  )
}

function ContractsTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const [modal, setModal] = useState(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('active')
  const [urgentOnly, setUrgentOnly] = useState(false)

  const { data: contracts = [], isLoading } = useQuery({ queryKey: ['alm-contracts'], queryFn: () => api.get('/alm/contracts').then(r => r.data) })
  const { data: vendors = [] } = useQuery({ queryKey: ['alm-vendors'], queryFn: () => api.get('/alm/vendors').then(r => r.data) })
  const { data: users = [] } = useQuery({ queryKey: ['users'], queryFn: () => api.get('/users').then(r => r.data) })
  const { data: costCenters = [] } = useQuery({ queryKey: ['alm-cost-centers'], queryFn: () => api.get('/alm/cost-centers').then(r => r.data) })

  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/alm/contracts/${id}`),
    onSuccess: () => { qc.invalidateQueries(['alm-contracts']); qc.invalidateQueries(['alm-dashboard']) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const filtered = contracts.filter(c =>
    (!search || c.title.toLowerCase().includes(search.toLowerCase()) || c.vendor_name?.toLowerCase().includes(search.toLowerCase())) &&
    (!statusFilter || c.status === statusFilter) &&
    (!urgentOnly || c.renewal_urgent)
  )

  const totalAnnual = filtered.reduce((s, c) => s + (c.annual_value || 0), 0)

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar contrato o proveedor..."
          style={{ ...fs, flex: 2, minWidth: 200 }} />
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ ...fs, flex: '0 0 160px' }}>
          <option value="">Todos los estados</option>
          {Object.entries(CONTRACT_STATUS).map(([k,v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <button onClick={() => setUrgentOnly(u => !u)}
          style={{ padding: '8px 14px', borderRadius: 8, border: `1px solid ${urgentOnly ? 'var(--danger-border)' : 'var(--surface-4)'}`, background: urgentOnly ? 'rgba(248,113,113,0.06)' : 'transparent', color: urgentOnly ? 'var(--danger)' : 'var(--text-2)', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>
          ⚠️ Solo urgentes
        </button>
        <Button onClick={() => setModal({})} icon="＋">Nuevo contrato</Button>
      </div>

      {filtered.length > 0 && (
        <div style={{ marginBottom: 16, padding: '10px 16px', background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, fontSize: 13, color: 'var(--text-2)' }}>
          {filtered.length} contrato(s) · Coste anual total: <strong style={{ color: 'var(--warning)' }}>{fmtCurrency(totalAnnual)}</strong>
        </div>
      )}

      {isLoading ? <Spinner /> : filtered.length === 0 ? (
        <EmptyState icon="📄" title="Sin contratos" description="Registra los contratos con tus proveedores de software, hardware y servicios" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {filtered.map(c => {
            const _st = CONTRACT_STATUS[c.status] || { label: c.status, color: 'var(--text-2)' }
            const ct = CONTRACT_TYPES[c.type] || { label: c.type, icon: '📄' }
            return (
              <div key={c.id} style={{ ...card, padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 14 }}>
                <div style={{ fontSize: 24, flexShrink: 0 }}>{ct.icon}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
                    <span style={{ fontSize: 14, fontWeight: 700 }}>{c.title}</span>
                    <StatusBadge status={c.status} cfg={CONTRACT_STATUS} />
                    {c.renewal_urgent && <span style={{ fontSize: 11, color: 'var(--danger)', fontWeight: 700 }}>⚠️ RENUEVA EN {c.days_to_renewal}d</span>}
                  </div>
                  <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'var(--text-2)', flexWrap: 'wrap' }}>
                    {c.vendor_name && <span>🏢 {c.vendor_name}</span>}
                    {c.annual_value && <span>💰 {fmtCurrency(c.annual_value)}/año</span>}
                    {c.renewal_date && <span>🔄 Renovar: {fmtDate(c.renewal_date)}</span>}
                    {c.owner_name && <span>👤 {c.owner_name}</span>}
                    {c.linked_clients?.map(cl => (
                      <span key={cl.id} style={{ color: 'var(--accent)', background: 'var(--accent-muted)', padding: '1px 6px', borderRadius: 4 }}>👤 {cl.name}</span>
                    ))}
                    <span>{ct.label}</span>
                    <span>{c.licenses_count} licencia(s)</span>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                  <button onClick={() => setModal(c)} style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '5px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12 }}>✏️</button>
                  <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar el contrato "${c.title}"?`, onConfirm: () => del(c.id), danger: true }) }}
                    style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '5px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 12 }}>🗑</button>
                </div>
              </div>
            )
          })}
        </div>
      )}
      {modal !== null && <ContractModal contract={Object.keys(modal).length ? modal : null} vendors={vendors} users={users} costCenters={costCenters} onClose={() => setModal(null)} />}
    </div>
  )
}

// ── Licenses ───────────────────────────────────────────────────────────────────
function LicenseAssignModal({ license, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const { data: users = [] } = useQuery({ queryKey: ['users'], queryFn: () => api.get('/users').then(r => r.data) })
  const { data: assets = [] } = useQuery({ queryKey: ['alm-assets'], queryFn: () => api.get('/alm/assets').then(r => r.data) })
  const [form, setForm] = useState({ user_id: '', asset_id: '', project_id: '', expires_at: '', notes: '' })
  const s = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  const availSeats = license.total_seats ? license.total_seats - (license.used_seats || 0) : null
  const { mutate, isPending } = useMutation({
    mutationFn: d => api.post(`/alm/licenses/${license.id}/assign`, d),
    onSuccess: () => { qc.invalidateQueries(['alm-licenses']); qc.invalidateQueries(['alm-license', license.id]); onClose() },
    onError: e => toast.error(extractErr(e, 'Error al asignar')),
  })
  return (
    <Modal open onClose={onClose} title={`Asignar licencia: ${license.name}`} width={520}>
      {availSeats !== null && (
        <div style={{ padding: '10px 14px', background: availSeats > 0 ? 'var(--success-bg)' : 'var(--danger-bg)', border: `1px solid ${availSeats > 0 ? 'var(--success-border)' : 'var(--danger-border)'}`, borderRadius: 8, marginBottom: 16, fontSize: 13 }}>
          {availSeats > 0 ? `✅ ${availSeats} seat(s) disponibles de ${license.total_seats}` : `❌ Sin seats disponibles (${license.used_seats}/${license.total_seats})`}
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label style={ls}>Asignar a usuario</label>
          <select value={form.user_id} onChange={s('user_id')} style={fs}>
            <option value="">Sin usuario específico</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name} ({u.email})</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Asignar a dispositivo</label>
          <select value={form.asset_id} onChange={s('asset_id')} style={fs}>
            <option value="">Sin dispositivo</option>
            {assets.map(a => <option key={a.id} value={a.id}>{ASSET_TYPES[a.type]?.icon} {a.name} {a.serial_number ? `(${a.serial_number})` : ''}</option>)}
          </select>
        </div>
        <div><label style={ls}>Fecha expiración asignación</label><input type="date" value={form.expires_at} onChange={s('expires_at')} style={fs} /></div>
        <div><label style={ls}>Notas</label><textarea value={form.notes} onChange={s('notes')} rows={2} style={{ ...fs, resize: 'vertical' }} /></div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
        <Button variant="secondary" onClick={onClose}>Cancelar</Button>
        <Button onClick={() => mutate(form)} disabled={isPending || (!form.user_id && !form.asset_id)} loading={isPending}>
          {isPending ? 'Asignando...' : 'Confirmar asignación'}
        </Button>
      </div>
    </Modal>
  )
}

function LicenseModal({ license, vendors, contracts, costCenters, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const isEdit = !!license?.id
  const [form, setForm] = useState({
    name: license?.name || '', product_name: license?.product_name || '',
    version: license?.version || '', edition: license?.edition || '',
    type: license?.type || 'subscription', platform: license?.platform || 'any',
    vendor_id: license?.vendor_id || '', contract_id: license?.contract_id || '',
    total_seats: license?.total_seats || '', license_key: '',
    purchase_date: license?.purchase_date || '', expiry_date: license?.expiry_date || '',
    purchase_price: license?.purchase_price || '', annual_cost: license?.annual_cost || '',
    cost_center_id: license?.cost_center_id || '', environment: license?.environment || 'all',
    is_compliance_req: license?.is_compliance_req ?? false, notes: license?.notes || '',
  })
  const s = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit ? api.patch(`/alm/licenses/${license.id}`, d) : api.post('/alm/licenses', d),
    onSuccess: () => { qc.invalidateQueries(['alm-licenses']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar licencia' : 'Nueva licencia'} width={720}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}><label style={ls}>Nombre *</label><input value={form.name} onChange={s('name')} style={fs} placeholder="Microsoft 365 — Plan Business Premium" /></div>
        <div><label style={ls}>Producto</label><input value={form.product_name} onChange={s('product_name')} style={fs} placeholder="Microsoft 365" /></div>
        <div><label style={ls}>Edición</label><input value={form.edition} onChange={s('edition')} style={fs} placeholder="Business Premium" /></div>
        <div><label style={ls}>Versión</label><input value={form.version} onChange={s('version')} style={fs} placeholder="2024" /></div>
        <div>
          <label style={ls}>Tipo de licencia</label>
          <select value={form.type} onChange={s('type')} style={fs}>
            {Object.entries(LICENSE_TYPES).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Plataforma</label>
          <select value={form.platform} onChange={s('platform')} style={fs}>
            {[['any','Todas'],['windows','Windows'],['mac','macOS'],['linux','Linux'],['web','Web'],['mobile','Móvil']].map(([k,l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Proveedor</label>
          <select value={form.vendor_id} onChange={s('vendor_id')} style={fs}>
            <option value="">Sin proveedor</option>
            {vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Contrato vinculado</label>
          <select value={form.contract_id} onChange={s('contract_id')} style={fs}>
            <option value="">Sin contrato</option>
            {contracts.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
        </div>
        <div><label style={ls}>Seats totales (vacío = ilimitado)</label><input type="number" value={form.total_seats} onChange={s('total_seats')} style={fs} placeholder="10" /></div>
        <div><label style={ls}>Coste anual (€)</label><input type="number" value={form.annual_cost} onChange={s('annual_cost')} style={fs} /></div>
        <div><label style={ls}>Precio compra (€)</label><input type="number" value={form.purchase_price} onChange={s('purchase_price')} style={fs} /></div>
        <div>
          <label style={ls}>Centro de coste</label>
          <select value={form.cost_center_id} onChange={s('cost_center_id')} style={fs}>
            <option value="">Sin centro de coste</option>
            {costCenters.map(c => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
          </select>
        </div>
        <div><label style={ls}>Fecha compra</label><input type="date" value={form.purchase_date} onChange={s('purchase_date')} style={fs} /></div>
        <div><label style={ls}>Fecha expiración</label><input type="date" value={form.expiry_date} onChange={s('expiry_date')} style={fs} /></div>
        <div>
          <label style={ls}>Entorno</label>
          <select value={form.environment} onChange={s('environment')} style={fs}>
            {[['all','Todos'],['prod','Producción'],['staging','Staging'],['dev','Desarrollo']].map(([k,l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingTop: 20 }}>
          <input type="checkbox" id="compliance" checked={form.is_compliance_req} onChange={e => setForm(f => ({ ...f, is_compliance_req: e.target.checked }))} />
          <label htmlFor="compliance" style={{ fontSize: 13, cursor: 'pointer' }}>Requiere compliance / auditoría</label>
        </div>
        <div style={{ gridColumn: '1/-1' }}><label style={ls}>Clave de licencia</label><input value={form.license_key} onChange={s('license_key')} style={{ ...fs, fontFamily: 'monospace' }} placeholder="XXXXX-XXXXX-XXXXX (guardado cifrado)" /></div>
        <div style={{ gridColumn: '1/-1' }}><label style={ls}>Notas</label><textarea value={form.notes} onChange={s('notes')} rows={3} style={{ ...fs, resize: 'vertical' }} /></div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
        <Button variant="secondary" onClick={onClose}>Cancelar</Button>
        <Button onClick={() => mutate(form)} disabled={isPending || !form.name} loading={isPending}>
          {isPending ? 'Guardando...' : isEdit ? 'Guardar' : 'Crear licencia'}
        </Button>
      </div>
    </Modal>
  )
}

function LicensesTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const [modal, setModal] = useState(null)
  const [assignModal, setAssignModal] = useState(null)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const { data: licenses = [], isLoading } = useQuery({ queryKey: ['alm-licenses'], queryFn: () => api.get('/alm/licenses').then(r => r.data) })
  const { data: vendors = [] } = useQuery({ queryKey: ['alm-vendors'], queryFn: () => api.get('/alm/vendors').then(r => r.data) })
  const { data: contracts = [] } = useQuery({ queryKey: ['alm-contracts'], queryFn: () => api.get('/alm/contracts').then(r => r.data) })
  const { data: costCenters = [] } = useQuery({ queryKey: ['alm-cost-centers'], queryFn: () => api.get('/alm/cost-centers').then(r => r.data) })

  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/alm/licenses/${id}`),
    onSuccess: () => qc.invalidateQueries(['alm-licenses']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const filtered = licenses.filter(l =>
    (!search || l.name.toLowerCase().includes(search.toLowerCase()) || l.vendor_name?.toLowerCase().includes(search.toLowerCase())) &&
    (!typeFilter || l.type === typeFilter) &&
    (!statusFilter || l.status === statusFilter)
  )

  const totalAnnual = filtered.reduce((s, l) => s + (l.annual_cost || 0), 0)
  const totalSeats  = filtered.reduce((s, l) => s + (l.total_seats || 0), 0)
  const usedSeats   = filtered.reduce((s, l) => s + (l.used_seats || 0), 0)

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar licencia..."
          style={{ ...fs, flex: 2, minWidth: 180 }} />
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)} style={{ ...fs, flex: '0 0 160px' }}>
          <option value="">Todos los tipos</option>
          {Object.entries(LICENSE_TYPES).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
        </select>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ ...fs, flex: '0 0 160px' }}>
          <option value="">Todos los estados</option>
          {Object.entries(LICENSE_STATUS_CFG).map(([k,v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <Button onClick={() => setModal({})} icon="＋">Nueva licencia</Button>
      </div>

      {filtered.length > 0 && (
        <div style={{ marginBottom: 16, padding: '10px 16px', background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, fontSize: 13, color: 'var(--text-2)', display: 'flex', gap: 20, flexWrap: 'wrap' }}>
          <span>{filtered.length} licencia(s)</span>
          {totalAnnual > 0 && <span>💰 <strong style={{ color: 'var(--warning)' }}>{fmtCurrency(totalAnnual)}</strong>/año</span>}
          {totalSeats > 0 && <span>🔑 {usedSeats}/{totalSeats} seats usados</span>}
        </div>
      )}

      {isLoading ? <Spinner /> : filtered.length === 0 ? (
        <EmptyState icon="🔑" title="Sin licencias" description="Registra las licencias de software de tu empresa para controlar su uso y coste" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {filtered.map(lic => {
            const _st = LICENSE_STATUS_CFG[lic.status] || { label: lic.status, color: 'var(--text-2)' }
            const lt = LICENSE_TYPES[lic.type] || { label: lic.type, icon: '🔑' }
            const pctUsed = lic.total_seats ? (lic.used_seats / lic.total_seats) * 100 : null
            const daysLeft = lic.days_to_expiry
            return (
              <div key={lic.id} style={{ ...card, padding: '16px 20px' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                  <div style={{ fontSize: 22, flexShrink: 0, marginTop: 2 }}>{lt.icon}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
                      <span style={{ fontSize: 14, fontWeight: 700 }}>{lic.name}</span>
                      <StatusBadge status={lic.status} cfg={LICENSE_STATUS_CFG} />
                      {lic.is_compliance_req && <span style={{ fontSize: 10, color: 'var(--warning)', border: '1px solid #ffb80040', borderRadius: 4, padding: '1px 5px' }}>COMPLIANCE</span>}
                      {daysLeft !== null && daysLeft <= 30 && daysLeft >= 0 && (
                        <span style={{ fontSize: 11, color: 'var(--danger)', fontWeight: 700 }}>⚠️ Expira en {daysLeft}d</span>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 14, fontSize: 12, color: 'var(--text-2)', flexWrap: 'wrap', marginBottom: 8 }}>
                      {lic.vendor_name && <span>🏢 {lic.vendor_name}</span>}
                      {lic.annual_cost && <span>💰 {fmtCurrency(lic.annual_cost)}/año</span>}
                      {lic.expiry_date && <span>📅 Expira: {fmtDate(lic.expiry_date)}</span>}
                      <span>{lt.label}</span>
                      {lic.linked_clients?.map(cl => (
                        <span key={cl.id} style={{ color: 'var(--accent)', background: 'var(--accent-muted)', padding: '1px 6px', borderRadius: 4 }}>👤 {cl.name}</span>
                      ))}
                      {lic.environment !== 'all' && <span>🌍 {lic.environment}</span>}
                    </div>
                    {lic.total_seats && (
                      <div style={{ marginBottom: 4 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>
                          <span>Seats usados</span>
                          <span style={{ color: pctUsed > 90 ? 'var(--danger)' : pctUsed > 75 ? 'var(--warning)' : 'var(--success)', fontWeight: 700 }}>
                            {lic.used_seats}/{lic.total_seats}
                          </span>
                        </div>
                        <div style={{ height: 5, background: 'var(--surface-4)', borderRadius: 3 }}>
                          <div style={{ height: '100%', width: `${Math.min(100, pctUsed)}%`, background: pctUsed > 100 ? 'var(--danger)' : pctUsed > 75 ? 'var(--warning)' : 'var(--success)', borderRadius: 3 }} />
                        </div>
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                    <button onClick={() => setAssignModal(lic)}
                      style={{ background: 'none', border: '1px solid #00d4ff30', borderRadius: 6, padding: '5px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: 12 }}>
                      👤 Asignar
                    </button>
                    <button onClick={() => setModal(lic)} style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '5px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12 }}>✏️</button>
                    <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar la licencia "${lic.name}"?`, onConfirm: () => del(lic.id), danger: true }) }}
                      style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '5px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 12 }}>🗑</button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
      {modal !== null && <LicenseModal license={Object.keys(modal).length ? modal : null} vendors={vendors} contracts={contracts} costCenters={costCenters} onClose={() => setModal(null)} />}
      {assignModal && <LicenseAssignModal license={assignModal} onClose={() => setAssignModal(null)} />}
    </div>
  )
}

// ── Assets ─────────────────────────────────────────────────────────────────────
function AssetModal({ asset, vendors, users, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const isEdit = !!asset?.id
  const [form, setForm] = useState({
    name: asset?.name || '', type: asset?.type || 'laptop',
    brand: asset?.brand || '', model: asset?.model || '',
    serial_number: asset?.serial_number || '', asset_tag: asset?.asset_tag || '',
    status: asset?.status || 'available', condition: asset?.condition || 'good',
    assigned_to_id: asset?.assigned_to_id || '', location: asset?.location || '',
    vendor_id: asset?.vendor_id || '',
    purchase_date: asset?.purchase_date || '', purchase_price: asset?.purchase_price || '',
    warranty_expiry: asset?.warranty_expiry || '', depreciation_years: asset?.depreciation_years || 3,
    ip_address: asset?.ip_address || '', hostname: asset?.hostname || '',
    os: asset?.os || '', cpu: asset?.cpu || '', ram_gb: asset?.ram_gb || '', storage_gb: asset?.storage_gb || '',
    notes: asset?.notes || '',
  })
  const s = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  const showNetwork = ['server','vm','network','desktop'].includes(form.type)
  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit ? api.patch(`/alm/assets/${asset.id}`, d) : api.post('/alm/assets', d),
    onSuccess: () => { qc.invalidateQueries(['alm-assets']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar activo' : 'Nuevo activo'} width={720}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}><label style={ls}>Nombre *</label><input value={form.name} onChange={s('name')} style={fs} placeholder="MacBook Pro 16 — Oriol" /></div>
        <div>
          <label style={ls}>Tipo</label>
          <select value={form.type} onChange={s('type')} style={fs}>
            {Object.entries(ASSET_TYPES).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Estado</label>
          <select value={form.status} onChange={s('status')} style={fs}>
            {Object.entries(ASSET_STATUS_CFG).map(([k,v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </div>
        <div><label style={ls}>Marca</label><input value={form.brand} onChange={s('brand')} style={fs} placeholder="Apple, Dell, HP..." /></div>
        <div><label style={ls}>Modelo</label><input value={form.model} onChange={s('model')} style={fs} /></div>
        <div><label style={ls}>Número de serie</label><input value={form.serial_number} onChange={s('serial_number')} style={fs} /></div>
        <div><label style={ls}>Etiqueta de activo</label><input value={form.asset_tag} onChange={s('asset_tag')} style={fs} placeholder="ASSET-001" /></div>
        <div>
          <label style={ls}>Asignado a</label>
          <select value={form.assigned_to_id} onChange={s('assigned_to_id')} style={fs}>
            <option value="">Sin asignar</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
        </div>
        <div><label style={ls}>Ubicación</label><input value={form.location} onChange={s('location')} style={fs} placeholder="Oficina Barcelona / Rack A3" /></div>
        <div>
          <label style={ls}>Proveedor</label>
          <select value={form.vendor_id} onChange={s('vendor_id')} style={fs}>
            <option value="">Sin proveedor</option>
            {vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>Condición</label>
          <select value={form.condition} onChange={s('condition')} style={fs}>
            {[['new','Nuevo'],['good','Bueno'],['fair','Regular'],['poor','Deteriorado']].map(([k,l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
        <div><label style={ls}>Fecha compra</label><input type="date" value={form.purchase_date} onChange={s('purchase_date')} style={fs} /></div>
        <div><label style={ls}>Precio compra (€)</label><input type="number" value={form.purchase_price} onChange={s('purchase_price')} style={fs} /></div>
        <div><label style={ls}>Fin garantía</label><input type="date" value={form.warranty_expiry} onChange={s('warranty_expiry')} style={fs} /></div>
        <div><label style={ls}>Años amortización</label><input type="number" value={form.depreciation_years} onChange={s('depreciation_years')} style={fs} /></div>
        {showNetwork && <>
          <div><label style={ls}>IP</label><input value={form.ip_address} onChange={s('ip_address')} style={fs} placeholder="192.168.1.10" /></div>
          <div><label style={ls}>Hostname</label><input value={form.hostname} onChange={s('hostname')} style={fs} /></div>
          <div><label style={ls}>Sistema operativo</label><input value={form.os} onChange={s('os')} style={fs} placeholder="Ubuntu 22.04 LTS" /></div>
          <div><label style={ls}>CPU</label><input value={form.cpu} onChange={s('cpu')} style={fs} placeholder="Intel Xeon E5-2680" /></div>
          <div><label style={ls}>RAM (GB)</label><input type="number" value={form.ram_gb} onChange={s('ram_gb')} style={fs} /></div>
          <div><label style={ls}>Almacenamiento (GB)</label><input type="number" value={form.storage_gb} onChange={s('storage_gb')} style={fs} /></div>
        </>}
        <div style={{ gridColumn: '1/-1' }}><label style={ls}>Notas</label><textarea value={form.notes} onChange={s('notes')} rows={3} style={{ ...fs, resize: 'vertical' }} /></div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
        <Button variant="secondary" onClick={onClose}>Cancelar</Button>
        <Button onClick={() => mutate(form)} disabled={isPending || !form.name || !form.type} loading={isPending}>
          {isPending ? 'Guardando...' : isEdit ? 'Guardar' : 'Crear activo'}
        </Button>
      </div>
    </Modal>
  )
}

function AssetsTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const [modal, setModal] = useState(null)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const { data: assets = [], isLoading } = useQuery({ queryKey: ['alm-assets'], queryFn: () => api.get('/alm/assets').then(r => r.data) })
  const { data: vendors = [] } = useQuery({ queryKey: ['alm-vendors'], queryFn: () => api.get('/alm/vendors').then(r => r.data) })
  const { data: users = [] } = useQuery({ queryKey: ['users'], queryFn: () => api.get('/users').then(r => r.data) })

  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/alm/assets/${id}`),
    onSuccess: () => qc.invalidateQueries(['alm-assets']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const filtered = assets.filter(a =>
    (!search || a.name.toLowerCase().includes(search.toLowerCase()) || a.serial_number?.toLowerCase().includes(search.toLowerCase()) || a.asset_tag?.toLowerCase().includes(search.toLowerCase())) &&
    (!typeFilter || a.type === typeFilter) &&
    (!statusFilter || a.status === statusFilter)
  )

  const totalValue     = filtered.reduce((s, a) => s + (a.purchase_price || 0), 0)
  const totalBookValue = filtered.reduce((s, a) => s + (a.book_value || 0), 0)

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar activo, serie, tag..."
          style={{ ...fs, flex: 2, minWidth: 180 }} />
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)} style={{ ...fs, flex: '0 0 160px' }}>
          <option value="">Todos los tipos</option>
          {Object.entries(ASSET_TYPES).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
        </select>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ ...fs, flex: '0 0 160px' }}>
          <option value="">Todos los estados</option>
          {Object.entries(ASSET_STATUS_CFG).map(([k,v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <Button onClick={() => setModal({})} icon="＋">Nuevo activo</Button>
      </div>

      {filtered.length > 0 && (
        <div style={{ marginBottom: 16, padding: '10px 16px', background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, fontSize: 13, color: 'var(--text-2)', display: 'flex', gap: 20, flexWrap: 'wrap' }}>
          <span>{filtered.length} activo(s)</span>
          {totalValue > 0 && <span>💰 Valor compra: <strong style={{ color: 'var(--accent)' }}>{fmtCurrency(totalValue)}</strong></span>}
          {totalBookValue > 0 && <span>📊 Valor libros: <strong style={{ color: 'var(--success)' }}>{fmtCurrency(totalBookValue)}</strong></span>}
        </div>
      )}

      {isLoading ? <Spinner /> : filtered.length === 0 ? (
        <EmptyState icon="🖥️" title="Sin activos" description="Inventaría los dispositivos y equipos de tu empresa" />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
          {filtered.map(a => {
            const at = ASSET_TYPES[a.type] || ASSET_TYPES.other
            const _st = ASSET_STATUS_CFG[a.status] || { label: a.status, color: 'var(--text-2)' }
            return (
              <div key={a.id} style={{ ...card, padding: '16px 18px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 22 }}>{at.icon}</span>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 700 }}>{a.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{a.brand} {a.model}</div>
                    </div>
                  </div>
                  <StatusBadge status={a.status} cfg={ASSET_STATUS_CFG} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3, fontSize: 12, color: 'var(--text-2)', marginBottom: 10 }}>
                  {a.assigned_to_name && <span>👤 {a.assigned_to_name}</span>}
                  {a.location         && <span>📍 {a.location}</span>}
                  {a.serial_number    && <span>🔢 S/N: {a.serial_number}</span>}
                  {a.asset_tag        && <span>🏷️ Tag: {a.asset_tag}</span>}
                  {a.warranty_expiry  && <span style={{ color: a.warranty_expired ? 'var(--danger)' : 'var(--text-2)' }}>🛡️ Garantía: {fmtDate(a.warranty_expiry)} {a.warranty_expired ? '⚠️' : ''}</span>}
                  {a.purchase_price   && <span>💰 {fmtCurrency(a.purchase_price)} → libros: {fmtCurrency(a.book_value || 0)}</span>}
                  {a.installed_licenses > 0 && <span>📦 {a.installed_licenses} licencia(s) instalada(s)</span>}
                </div>
                <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                  <button onClick={() => setModal(a)} style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12 }}>✏️</button>
                  <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar el activo "${a.name}"?`, onConfirm: () => del(a.id), danger: true }) }}
                    style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 12 }}>🗑</button>
                </div>
              </div>
            )
          })}
        </div>
      )}
      {modal !== null && <AssetModal asset={Object.keys(modal).length ? modal : null} vendors={vendors} users={users} onClose={() => setModal(null)} />}
    </div>
  )
}

// ── Cost Centers ───────────────────────────────────────────────────────────────
function CostCentersTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({ code: '', name: '', description: '', budget_annual: '', currency: 'EUR' })
  const s = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  const { data: centers = [], isLoading } = useQuery({ queryKey: ['alm-cost-centers'], queryFn: () => api.get('/alm/cost-centers').then(r => r.data) })

  const { mutate: save, isPending } = useMutation({
    mutationFn: d => editing ? api.patch(`/alm/cost-centers/${editing.id}`, d) : api.post('/alm/cost-centers', d),
    onSuccess: () => { qc.invalidateQueries(['alm-cost-centers']); setShowForm(false); setEditing(null); setForm({ code: '', name: '', description: '', budget_annual: '', currency: 'EUR' }) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/alm/cost-centers/${id}`),
    onSuccess: () => qc.invalidateQueries(['alm-cost-centers']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const openEdit = (c) => { setEditing(c); setForm({ code: c.code, name: c.name, description: c.description || '', budget_annual: c.budget_annual || '', currency: c.currency || 'EUR' }); setShowForm(true) }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button onClick={() => { setEditing(null); setShowForm(true) }} icon="＋">Nuevo centro de coste</Button>
      </div>
      {showForm && (
        <div style={{ ...card, padding: 20, marginBottom: 20 }}>
          <h4 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 700 }}>{editing ? 'Editar' : 'Nuevo'} centro de coste</h4>
          <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr 120px', gap: 12 }}>
            <div><label style={ls}>Código *</label><input value={form.code} onChange={s('code')} style={fs} placeholder="CC-001" /></div>
            <div><label style={ls}>Nombre *</label><input value={form.name} onChange={s('name')} style={fs} placeholder="Tecnología" /></div>
            <div><label style={ls}>Presupuesto anual (€)</label><input type="number" value={form.budget_annual} onChange={s('budget_annual')} style={fs} /></div>
            <div><label style={ls}>Moneda</label><input value={form.currency} onChange={s('currency')} style={fs} /></div>
            <div style={{ gridColumn: '1/-1' }}><label style={ls}>Descripción</label><input value={form.description} onChange={s('description')} style={fs} /></div>
          </div>
          <div style={{ display: 'flex', gap: 10, marginTop: 14, justifyContent: 'flex-end' }}>
            <Button variant="secondary" onClick={() => { setShowForm(false); setEditing(null) }}>Cancelar</Button>
            <Button onClick={() => save(form)} disabled={isPending || !form.code || !form.name} loading={isPending}>{isPending ? 'Guardando...' : editing ? 'Guardar' : 'Crear'}</Button>
          </div>
        </div>
      )}
      {isLoading ? <Spinner /> : centers.length === 0 ? (
        <EmptyState icon="💼" title="Sin centros de coste" description="Define los centros de coste para asignar el gasto de licencias y contratos" />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
          {centers.map(c => (
            <div key={c.id} style={{ ...card, padding: '16px 18px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <div>
                  <span style={{ fontSize: 11, fontFamily: 'monospace', color: 'var(--accent)', fontWeight: 700 }}>{c.code}</span>
                  <div style={{ fontSize: 14, fontWeight: 700, marginTop: 2 }}>{c.name}</div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={() => openEdit(c)} style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12 }}>✏️</button>
                  <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar el centro de coste "${c.name}"?`, onConfirm: () => del(c.id), danger: true }) }}
                    style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: 12 }}>🗑</button>
                </div>
              </div>
              {c.budget_annual && <div style={{ fontSize: 13, color: 'var(--warning)', fontWeight: 600 }}>{fmtCurrency(c.budget_annual)}/año</div>}
              {c.description && <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 4 }}>{c.description}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Compliance ─────────────────────────────────────────────────────────────────
function ComplianceTab() {
  const { data: report = {}, isLoading, refetch } = useQuery({
    queryKey: ['alm-compliance'],
    queryFn: () => api.get('/alm/compliance').then(r => r.data),
  })
  const issues = report.issues || []

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
        <div>
          <p style={{ color: 'var(--text-2)', fontSize: 14, margin: 0 }}>
            Auditoría automática de licencias marcadas como compliance obligatorio. Detecta vencimientos y sobreasignaciones.
          </p>
        </div>
        <Button onClick={() => refetch()} variant="secondary">🔄 Actualizar</Button>
      </div>

      {isLoading ? <Spinner /> : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 24 }}>
            <div style={{ ...card, padding: '18px 20px', borderColor: issues.length === 0 ? 'var(--success-border)' : 'var(--danger-border)' }}>
              <div style={{ fontSize: 28, marginBottom: 8 }}>{issues.length === 0 ? '✅' : '❌'}</div>
              <div style={{ fontSize: 22, fontWeight: 800, color: issues.length === 0 ? 'var(--success)' : 'var(--danger)' }}>{issues.length}</div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Problemas de compliance</div>
            </div>
            <div style={{ ...card, padding: '18px 20px' }}>
              <div style={{ fontSize: 28, marginBottom: 8 }}>🔴</div>
              <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--danger)' }}>{report.critical || 0}</div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Críticos (acción inmediata)</div>
            </div>
          </div>

          {issues.length === 0 ? (
            <div style={{ ...card, padding: '40px 20px', textAlign: 'center' }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>✅</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--success)', marginBottom: 8 }}>Compliance OK</div>
              <div style={{ fontSize: 13, color: 'var(--text-2)' }}>Todas las licencias de compliance están activas y correctamente asignadas</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {issues.map((iss, idx) => (
                <div key={idx} style={{ ...card, padding: '14px 18px', borderColor: iss.severity === 'critical' ? 'var(--danger-border)' : 'rgba(245,158,11,0.31)', background: iss.severity === 'critical' ? 'var(--danger-bg)' : 'rgba(245,158,11,0.04)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>{iss.name}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{iss.detail}</div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 9px', borderRadius: 20, background: 'var(--danger-bg)', color: 'var(--danger)', border: '1px solid #ff475740' }}>
                        {iss.issue}
                      </span>
                      <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 9px', borderRadius: 20, background: iss.severity === 'critical' ? 'var(--danger-bg)' : 'var(--warning-bg)', color: iss.severity === 'critical' ? 'var(--danger)' : 'var(--warning)', border: `1px solid ${iss.severity === 'critical' ? 'rgba(248,113,113,0.25)' : 'rgba(245,158,11,0.25)'}` }}>
                        {iss.severity === 'critical' ? 'CRÍTICO' : 'AVISO'}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────────────
export default function ALMPage() {
  const _t = useAppT()
  const [tab, setTab] = useState('dashboard')

  const TABS = [
    { id: 'dashboard',   label: '📊 Dashboard',         desc: 'KPIs y renovaciones' },
    { id: 'vendors',     label: '🏢 Proveedores',        desc: 'Gestión de proveedores' },
    { id: 'contracts',   label: '📄 Contratos',          desc: 'Contratos activos' },
    { id: 'licenses',    label: '🔑 Licencias',          desc: 'Software y suscripciones' },
    { id: 'assets',      label: '🖥️ Activos',            desc: 'Hardware e inventario' },
    { id: 'cost',        label: '💼 Centros de coste',   desc: 'Asignación de costes' },
    { id: 'compliance',  label: '✅ Compliance',          desc: 'Auditoría de licencias' },
  ]

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        title="Gestión de Licencias y Activos"
        subtitle="Proveedores · Contratos · Licencias · Hardware · Compliance"
      />

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 24, flexWrap: 'wrap' }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{
              padding: '8px 16px', borderRadius: 10,
              border: `1px solid ${tab === t.id ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
              background: tab === t.id ? 'var(--accent-muted)' : 'transparent',
              color: tab === t.id ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
              transition: 'all 0.15s',
            }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {tab === 'dashboard'  && <ALMDashboard onNavigate={setTab} />}
      {tab === 'vendors'    && <VendorsTab />}
      {tab === 'contracts'  && <ContractsTab />}
      {tab === 'licenses'   && <LicensesTab />}
      {tab === 'assets'     && <AssetsTab />}
      {tab === 'cost'       && <CostCentersTab />}
      {tab === 'compliance' && <ComplianceTab />}
    </div>
  )
}
