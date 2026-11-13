import { useId, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import type { ZodSchema } from 'zod'
import { assetsApi, licensesApi, vendorsApi, almExtApi, usersApi, cmdbApi } from '../services/api'
import type { UserListItem } from '../services/api'
import { Button, Spinner, EmptyState, Modal, Tabs, Page } from '../components/ui'
import {
  Layers, Building2, FileText, Key, Monitor, Briefcase,
} from 'lucide-react'
import { fmtCurrency, fmtDate, extractErr, localeActivo } from '../utils/helpers'
import { sanitizeUrl } from '../utils/security'
import { useAppT } from '../i18n/AppLangContext'
import { useFormValidation } from '../hooks/useFormValidation'
import { useOrgSettings } from '../hooks/useOrgSettings'
import { alpha } from '../constants/theme'
import DsBadge from '../components/ui/StatusBadge'
import DateInput from '../components/ui/DateInput'
import { POLL_DEFAULT_MS } from '../constants/timings'
import { FULL_LIST_SIZE } from '../constants/pagination'

// ── Constantes ────────────────────────────────────────────────────────────────
type CatalogoIcono = { label: string; icon: string }
type CatalogoColor = { label: string; color: string }

const VENDOR_CATS: Record<string, CatalogoIcono & { color: string }> = {
  software:   { label: 'Software',    icon: '💻', color: 'var(--accent)' },
  hardware:   { label: 'Hardware',    icon: '🖥️', color: 'var(--purple)' },
  saas:       { label: 'SaaS',        icon: '☁️', color: 'var(--success)' },
  cloud:      { label: 'Cloud',       icon: '⛅', color: 'var(--accent)' },
  telecom:    { label: 'Telecom',     icon: '📡', color: 'var(--warning)' },
  consulting: { label: 'Consultoría', icon: '🏢', color: 'var(--purple)' },
  other:      { label: 'Otro',        icon: '📦', color: 'var(--text-2)' },
}

const CONTRACT_TYPES: Record<string, CatalogoIcono> = {
  purchase:     { label: 'Compra',         icon: '🛒' },
  subscription: { label: 'Suscripción',    icon: '🔄' },
  maintenance:  { label: 'Mantenimiento',  icon: '🔧' },
  support:      { label: 'Soporte',        icon: '🎫' },
  lease:        { label: 'Arrendamiento',  icon: '📋' },
  enterprise:   { label: 'Enterprise',     icon: '🏛️' },
}

const CONTRACT_STATUS: Record<string, CatalogoColor> = {
  active:    { label: 'Activo',    color: 'var(--success)' },
  expired:   { label: 'Expirado', color: 'var(--danger)' },
  cancelled: { label: 'Cancelado',color: 'var(--text-2)' },
  pending:   { label: 'Pendiente',color: 'var(--warning)' },
  draft:     { label: 'Borrador', color: 'var(--text-3)' },
}

const LICENSE_TYPES: Record<string, CatalogoIcono> = {
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

const LICENSE_STATUS_CFG: Record<string, CatalogoColor> = {
  active:        { label: 'Activa',          color: 'var(--success)' },
  expired:       { label: 'Expirada',        color: 'var(--danger)' },
  unassigned:    { label: 'Sin asignar',     color: 'var(--text-2)' },
  overallocated: { label: 'Sobreasignada',   color: 'var(--danger)' },
  cancelled:     { label: 'Cancelada',       color: 'var(--text-3)' },
}

const ASSET_TYPES: Record<string, CatalogoIcono> = {
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

const ASSET_STATUS_CFG: Record<string, CatalogoColor> = {
  in_use:    { label: 'En uso',         color: 'var(--accent)' },
  available: { label: 'Disponible',     color: 'var(--success)' },
  in_repair: { label: 'En reparación',  color: 'var(--warning)' },
  retired:   { label: 'Retirado',       color: 'var(--text-2)' },
  lost:      { label: 'Perdido',        color: 'var(--danger)' },
  stolen:    { label: 'Robado',         color: 'var(--danger)' },
}

// ── Entidades (lo que devuelven los endpoints /alm/*) ─────────────────────────
type Referencia = { id: string; name: string }
type Vendor = {
  id: string
  name: string
  category?: string
  website?: string | null
  support_email?: string | null
  support_phone?: string | null
  account_manager?: string | null
  account_number?: string | null
  tax_id?: string | null
  country?: string | null
  notes?: string | null
  contracts_count?: number
}
type AlmContract = {
  id: string
  title: string
  vendor_id?: string | null
  vendor_name?: string | null
  type?: string
  status?: string
  start_date?: string | null
  end_date?: string | null
  renewal_date?: string | null
  auto_renew?: boolean
  notice_days?: number | null
  resolution_hours?: number | null
  response_hours?: number | null
  total_value?: number | null
  annual_value?: number | null
  billing_cycle?: string | null
  currency?: string | null
  payment_method?: string | null
  po_number?: string | null
  cost_center_id?: string | null
  owner_id?: string | null
  owner_name?: string | null
  document_url?: string | null
  notes?: string | null
  tags?: string | null
  renewal_urgent?: boolean
  days_to_renewal?: number | null
  licenses_count?: number
  linked_clients?: Referencia[]
}
type License = {
  id: string
  name: string
  product_name?: string | null
  version?: string | null
  edition?: string | null
  type?: string
  platform?: string | null
  status?: string
  vendor_id?: string | null
  vendor_name?: string | null
  contract_id?: string | null
  total_seats?: number | null
  used_seats?: number | null
  purchase_date?: string | null
  expiry_date?: string | null
  days_to_expiry?: number | null
  purchase_price?: number | null
  annual_cost?: number | null
  cost_center_id?: string | null
  environment?: string | null
  is_compliance_req?: boolean
  notes?: string | null
  linked_clients?: Referencia[]
}
type Asset = {
  id: string
  name: string
  type?: string
  brand?: string | null
  model?: string | null
  serial_number?: string | null
  asset_tag?: string | null
  status?: string
  condition?: string | null
  assigned_to_id?: string | null
  assigned_to_name?: string | null
  location?: string | null
  vendor_id?: string | null
  purchase_date?: string | null
  purchase_price?: number | null
  book_value?: number | null
  warranty_expiry?: string | null
  warranty_expired?: boolean
  depreciation_years?: number | null
  ip_address?: string | null
  hostname?: string | null
  os?: string | null
  cpu?: string | null
  ram_gb?: number | null
  storage_gb?: number | null
  notes?: string | null
  installed_licenses?: number
  ci_id?: string | null
  ci_code?: string | null
  ci_name?: string | null
  eol_date?: string | null
  lease_expiry?: string | null
  next_maintenance_date?: string | null
  maintenance_contract?: string | null
}
type CostCenter = { id: string; code: string; name: string; description?: string | null; budget_annual?: number | null; currency?: string | null }
type CostCenterForm = { code: string; name: string; description: string; budget_annual: string | number; currency: string }
type AlmKpis = {
  total_contracts?: number
  expiring_soon?: number
  total_licenses?: number
  expired_licenses?: number
  total_assets?: number
  assets_in_use?: number
  total_vendors?: number
  annual_license_cost?: number
  total_annual_cost?: number
}
type Renovacion = { id: string; title: string; vendor_name?: string | null; days_to_renewal: number; renewal_date?: string | null }
type AlmDashboardData = { kpis?: AlmKpis; upcoming_renewals?: Renovacion[] }
type CmdbItem = { id: string; code?: string; name: string }
type AssetHistoryRow = { id: string; field: string; old_value?: string | null; new_value?: string | null; changed_at?: string | null; user_name?: string | null; note?: string | null }
type ExpiringRow = { asset_id: string; name: string; expiry_type: string; expiry_date: string; days_remaining: number; refresh_ticket_id?: string | null }
type RefreshTicketResult = { created: boolean; number: string }
type ComplianceIssue = { name: string; detail?: string; issue: string; severity: string }
type ComplianceReport = { issues?: ComplianceIssue[]; critical?: number }
/** Cambio de un campo de texto, select, textarea o DateInput. */
type CambioDeCampo = { target: { value: string } }
/** Lo que `useFormValidation(esquema)` entrega como datos válidos. */
type DatosValidos<S> = S extends ZodSchema<infer T> ? T : never

// ── Estilos compartidos ───────────────────────────────────────────────────────
const card: CSSProperties  = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const fs: CSSProperties    = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', width: '100%' }
const ls: CSSProperties    = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 6 }

const StatusBadge = ({ status, cfg }: { status: string; cfg: Record<string, CatalogoColor> }) => {
  const c = cfg[status] || { label: status, color: 'var(--text-2)' }
  return (
    <DsBadge color={c.color} caps={false}>{c.label}</DsBadge>
  )
}

const KPI = ({ icon, label, value, sub, color = 'var(--accent)', alert }: { icon: ReactNode; label: ReactNode; value: ReactNode; sub?: ReactNode; color?: string; alert?: boolean }) => (
  <div style={{ ...card, padding: '20px 22px', display: 'flex', gap: 14, alignItems: 'center',
    ...(alert ? { borderColor: 'var(--danger-border)', background: 'var(--danger-bg)' } : {}) }}>
    <div style={{ fontSize: "var(--text-3xl)", flexShrink: 0 }}>{icon}</div>
    <div>
      <div style={{ fontSize: "var(--text-2xl)", fontWeight: 800, color, lineHeight: 1.1 }}>{value}</div>
      <div style={{ fontSize: "var(--text-base)", fontWeight: 600, marginTop: 2 }}>{label}</div>
      {sub && <div className="u-text2-xs-mt2">{sub}</div>}
    </div>
  </div>
)

const SectionTitle = ({ children, action }: { children: ReactNode; action?: ReactNode }) => (
  <div className="u-row-between-mb16">
    <h3 style={{ fontSize: "var(--text-md-em)", fontWeight: 700, margin: 0 }}>{children}</h3>
    {action}
  </div>
)


// ── Dashboard ALM ─────────────────────────────────────────────────────────────
function ALMDashboard({ onNavigate }: { onNavigate: (tab: string) => void }) {
  const t = useAppT()
  const { data: dash = {}, isLoading } = useQuery<AlmDashboardData>({
    queryKey: ['alm-dashboard'],
    queryFn: () => almExtApi.dashboard().then(r => r.data),
    refetchInterval: POLL_DEFAULT_MS,
  })
  const kpis: AlmKpis = dash.kpis || {}
  const renewals = dash.upcoming_renewals || []

  if (isLoading) return <div style={{ padding: 40, textAlign: 'center' }}><Spinner size={32} /></div>

  return (
    <div>
      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 14, marginBottom: 28 }}>
        <KPI icon="📄" label={t('alm.dashboard_contracts_active')}        value={kpis.total_contracts ?? 0}   color="var(--accent)"
          sub={kpis.expiring_soon ? `${kpis.expiring_soon} ${t('alm.dashboard_expire_60')}` : undefined}
          alert={kpis.expiring_soon > 0} />
        <KPI icon="🔑" label={t('alm.dashboard_licenses_managed')}   value={kpis.total_licenses ?? 0}    color="var(--purple)"
          sub={kpis.expired_licenses ? `${kpis.expired_licenses} ${t('alm.dashboard_expired')}` : undefined}
          alert={kpis.expired_licenses > 0} />
        <KPI icon="🖥️" label={t('alm.dashboard_assets_inventory')}  value={kpis.total_assets ?? 0}       color="var(--success)"
          sub={`${kpis.assets_in_use ?? 0} ${t('alm.dashboard_in_use')}`} />
        <KPI icon="🏢" label={t('alm.dashboard_vendors_active')}     value={kpis.total_vendors ?? 0}      color="var(--orange)" />
        <KPI icon="💰" label={t('alm.dashboard_license_annual_cost')}   value={fmtCurrency(kpis.annual_license_cost ?? 0)} color="var(--warning)" sub={t('alm.dashboard_license_cost_scope')} />
        <KPI icon="📊" label={t('alm.dashboard_total_annual_cost')}       value={fmtCurrency(kpis.total_annual_cost ?? 0)}   color="var(--danger)" sub={t('alm.dashboard_total_cost_scope')} />
      </div>

      {/* Renovaciones próximas */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <div style={card}>
          <div style={{ padding: '18px 20px 14px' }}>
            <SectionTitle>{`⚠️ ${t('alm.dashboard_upcoming_renewals')}`}
              <Button onClick={() => onNavigate('contracts')} variant="secondary">{`${t('alm.dashboard_view_contracts')} →`}</Button>
            </SectionTitle>
            {renewals.length === 0 ? (
              <div style={{ padding: '20px 0', textAlign: 'center', color: 'var(--text-2)', fontSize: "var(--text-base)" }}>
                {`✅ ${t('alm.dashboard_no_urgent_renewals')}`}
              </div>
            ) : (
              renewals.map(c => (
                <div key={c.id} style={{ padding: '10px 0', borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div className="u-base-600">{c.title}</div>
                    <div className="u-text2-xs">{c.vendor_name}</div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0, marginLeft: 12 }}>
                    <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: c.days_to_renewal <= 14 ? 'var(--danger)' : c.days_to_renewal <= 30 ? 'var(--warning)' : 'var(--success)' }}>
                        {c.days_to_renewal === 0 ? t('alm.dashboard_today') : `${c.days_to_renewal}${t('alm.dashboard_days_short')}`}
                    </div>
                    <div className="u-text2-xs">{fmtDate(c.renewal_date)}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div style={card}>
          <div style={{ padding: '18px 20px 14px' }}>
            <SectionTitle>{`💡 ${t('alm.dashboard_quick_actions')}`}</SectionTitle>
            {[
              { icon: '🏢', label: t('alm.action_add_vendor'),   tab: 'vendors',   color: 'var(--accent)' },
              { icon: '📄', label: t('alm.action_new_contract'),      tab: 'contracts', color: 'var(--purple)' },
              { icon: '🔑', label: t('alm.action_register_license'),  tab: 'licenses',  color: 'var(--success)' },
              { icon: '🖥️', label: t('alm.action_add_asset'),      tab: 'assets',    color: 'var(--warning)' },
              { icon: '💼', label: t('alm.action_cost_centers'),    tab: 'cost',      color: 'var(--warning)' },
              { icon: '📊', label: t('alm.action_compliance_report'),  tab: 'compliance',color: 'var(--danger)' },
            ].map(a => (
              <button key={a.tab} onClick={() => onNavigate(a.tab)}
                style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-1)', fontSize: "var(--text-base)", cursor: 'pointer', fontFamily: 'inherit', marginBottom: 6, textAlign: 'left', transition: 'border-color 0.15s' }}
                onMouseEnter={e => e.currentTarget.style.borderColor = alpha(a.color, '60')}
                onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}>
                <span style={{ fontSize: "var(--text-lg)" }}>{a.icon}</span>
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
function VendorModal({ vendor, onClose }: { vendor: Partial<Vendor> | null; onClose: () => void }) {
  const t = useAppT()
  const idPrefix = useId()
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
  const s = (k: keyof typeof form) => (e: CambioDeCampo) => setForm(f => ({ ...f, [k]: e.target.value }))
  const { mutate, isPending } = useMutation({
    mutationFn: (d: typeof form) => isEdit ? vendorsApi.update(vendor.id, d) : vendorsApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['alm-vendors'] }); qc.invalidateQueries({ queryKey: ['alm-dashboard'] }); onClose() },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })
  return (
    <Modal open onClose={onClose} title={isEdit ? t('alm.vendor_modal_edit') : t('alm.vendor_modal_new')} width={640}>
      <div className="u-grid2-14">
        <div className="u-col-full"><label id={`${idPrefix}-name-et`} htmlFor={`${idPrefix}-name`} style={ls}>{t('alm.vendor_label_name')} *</label><input id={`${idPrefix}-name`} aria-labelledby={`${idPrefix}-name-et`} value={form.name} onChange={s('name')} style={fs} placeholder={t('alm.vendor_placeholder_name')} /></div>
        <div>
          <label htmlFor={`${idPrefix}-category`} style={ls}>{t('alm.vendor_label_category')}</label>
          <select id={`${idPrefix}-category`} value={form.category} onChange={s('category')} style={fs}>
            {Object.entries(VENDOR_CATS).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
          </select>
        </div>
        <div><label id={`${idPrefix}-country-et`} htmlFor={`${idPrefix}-country`} style={ls}>{t('alm.vendor_label_country')}</label><input id={`${idPrefix}-country`} aria-labelledby={`${idPrefix}-country-et`} value={form.country} onChange={s('country')} style={fs} placeholder={t('alm.ej_espana')} /></div>
        <div><label id={`${idPrefix}-website-et`} htmlFor={`${idPrefix}-website`} style={ls}>{t('alm.vendor_label_web')}</label><input id={`${idPrefix}-website`} aria-labelledby={`${idPrefix}-website-et`} value={form.website} onChange={s('website')} style={fs} placeholder={t('alm.vendor_placeholder_web')} /></div>
        <div><label id={`${idPrefix}-support-email-et`} htmlFor={`${idPrefix}-support-email`} style={ls}>{t('alm.vendor_label_support_email')}</label><input id={`${idPrefix}-support-email`} aria-labelledby={`${idPrefix}-support-email-et`} value={form.support_email} onChange={s('support_email')} style={fs} /></div>
        <div><label id={`${idPrefix}-support-phone-et`} htmlFor={`${idPrefix}-support-phone`} style={ls}>{t('alm.vendor_label_support_phone')}</label><input id={`${idPrefix}-support-phone`} aria-labelledby={`${idPrefix}-support-phone-et`} value={form.support_phone} onChange={s('support_phone')} style={fs} /></div>
        <div><label id={`${idPrefix}-account-manager-et`} htmlFor={`${idPrefix}-account-manager`} style={ls}>{t('alm.vendor_label_account_manager')}</label><input id={`${idPrefix}-account-manager`} aria-labelledby={`${idPrefix}-account-manager-et`} value={form.account_manager} onChange={s('account_manager')} style={fs} /></div>
        <div><label id={`${idPrefix}-account-number-et`} htmlFor={`${idPrefix}-account-number`} style={ls}>{t('alm.vendor_label_account_number')}</label><input id={`${idPrefix}-account-number`} aria-labelledby={`${idPrefix}-account-number-et`} value={form.account_number} onChange={s('account_number')} style={fs} /></div>
        <div><label id={`${idPrefix}-tax-id-et`} htmlFor={`${idPrefix}-tax-id`} style={ls}>{t('alm.vendor_label_tax_id')}</label><input id={`${idPrefix}-tax-id`} aria-labelledby={`${idPrefix}-tax-id-et`} value={form.tax_id} onChange={s('tax_id')} style={fs} /></div>
        <div className="u-col-full"><label id={`${idPrefix}-notes-et`} htmlFor={`${idPrefix}-notes`} style={ls}>{t('alm.vendor_label_notes')}</label><textarea id={`${idPrefix}-notes`} aria-labelledby={`${idPrefix}-notes-et`} value={form.notes} onChange={s('notes')} rows={3} style={{ ...fs, resize: 'vertical' }} /></div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => mutate(form)} disabled={isPending || !form.name} loading={isPending}>
          {isPending ? t('common.saving') : isEdit ? t('common.save') : t('alm.vendor_create')}
        </Button>
      </div>
    </Modal>
  )
}

function VendorsTab() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [modal, setModal] = useState<Partial<Vendor> | null>(null)
  const [search, setSearch] = useState('')
  const [catFilter, setCatFilter] = useState('')

  const { data: vendors = [], isLoading } = useQuery<Vendor[]>({
    queryKey: ['alm-vendors'],
    queryFn: () => vendorsApi.list(undefined).then(r => r.data),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id: string) => vendorsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-vendors'] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const filtered = vendors.filter(v =>
    (!search || v.name.toLowerCase().includes(search.toLowerCase())) &&
    (!catFilter || v.category === catFilter)
  )

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <input aria-label={t('alm.vendors_search_placeholder')} value={search} onChange={e => setSearch(e.target.value)} placeholder={t('alm.vendors_search_placeholder')}
          style={{ ...fs, flex: 2 }} />
        <select aria-label={t('alm.vendors_filter_aria')} value={catFilter} onChange={e => setCatFilter(e.target.value)} style={{ ...fs, flex: 1 }}>
          <option value="">{t('alm.vendors_filter_all_categories')}</option>
          {Object.entries(VENDOR_CATS).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
        </select>
        <Button onClick={() => setModal({})} icon="＋">{t('alm.vendors_new')}</Button>
      </div>

      {isLoading ? <Spinner /> : filtered.length === 0 ? (
        <EmptyState svgIcon={<Building2 size={36} />} title={t('alm.vendors_empty_title')} description={t('alm.vendors_empty_desc')} />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 }}>
          {filtered.map(v => {
            const cat = VENDOR_CATS[v.category] || VENDOR_CATS.other
            return (
              <div key={v.id} style={{ ...card, padding: '18px 20px', transition: 'border-color 0.15s' }}
                onPointerEnter={e => e.currentTarget.style.borderColor = alpha(cat.color, '50')}
                onPointerLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                  <div className="u-row-center-10">
                    <div style={{ width: 36, height: 36, borderRadius: 9, background: alpha(cat.color, '20'), display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-lg-em)" }}>
                      {cat.icon}
                    </div>
                    <div>
                      <div style={{ fontSize: "var(--text-md-em)", fontWeight: 700 }}>{v.name}</div>
                      <div style={{ fontSize: "var(--text-xs)", color: cat.color, fontWeight: 600 }}>{cat.label}</div>
                    </div>
                  </div>
                  <div className="u-row-6">
                    <button aria-label={`Editar proveedor ${v.name}`} onClick={() => setModal(v)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>✏️</button>
                    <button aria-label={`${t('common.delete')} ${v.name}`} onClick={() => { openConfirmGlobal({ message: `${t('alm.vendors_delete_confirm')} "${v.name}"?`, onConfirm: () => del(v.id), danger: true }) }}
                      style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '4px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>🗑</button>
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                  {v.account_manager && <span>👤 {v.account_manager}</span>}
                  {v.support_email   && <span>✉️ {v.support_email}</span>}
                  {v.website         && <a href={sanitizeUrl(v.website)} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', fontSize: "var(--text-sm)" }}>🔗 {v.website}</a>}
                </div>
                <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)', fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
                  {v.contracts_count} {t('alm.vendors_contracts_count')}
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
const almContractSchema = z.object({
  title: z.string().trim().min(1, 'El titulo es obligatorio'),
  vendor_id: z.union([z.string(), z.number()]).optional(),
  type: z.enum(['purchase', 'subscription', 'maintenance', 'support', 'lease', 'enterprise']),
  status: z.enum(['active', 'expired', 'cancelled', 'pending', 'draft']),
  start_date: z.string().optional(),
  end_date: z.string().optional(),
  renewal_date: z.string().optional(),
  auto_renew: z.boolean(),
  notice_days: z.coerce.number().int('Debe ser un entero').min(0, 'No puede ser negativo'),
  // UC: vacío se envía como null para poder quitar el plazo al editar.
  resolution_hours: z.preprocess((v) => (v === '' || v === undefined ? null : v), z.union([z.null(), z.coerce.number().positive('Horas mayores que cero')])),
  response_hours: z.preprocess((v) => (v === '' || v === undefined ? null : v), z.union([z.null(), z.coerce.number().positive('Horas mayores que cero')])),
  total_value: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, 'No puede ser negativo').optional()),
  annual_value: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, 'No puede ser negativo').optional()),
  billing_cycle: z.enum(['one_time', 'monthly', 'quarterly', 'annual', 'biennial']),
  currency: z.string().optional(),
  payment_method: z.string().optional(),
  po_number: z.string().optional(),
  cost_center_id: z.union([z.string(), z.number()]).optional(),
  owner_id: z.union([z.string(), z.number()]).optional(),
  document_url: z.string().optional(),
  notes: z.string().optional(),
  tags: z.string().optional(),
}).superRefine((values, ctx) => {
  if (values.start_date && values.end_date && values.end_date < values.start_date) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['end_date'], message: 'La fecha fin no puede ser anterior a la fecha inicio' })
  }
  if (values.start_date && values.renewal_date && values.renewal_date < values.start_date) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['renewal_date'], message: 'La fecha de renovacion no puede ser anterior a la fecha inicio' })
  }
})

const almLicenseAssignSchema = z.object({
  user_id: z.union([z.string(), z.number()]).optional(),
  asset_id: z.union([z.string(), z.number()]).optional(),
  project_id: z.union([z.string(), z.number()]).optional(),
  expires_at: z.string().optional(),
  notes: z.string().optional(),
}).superRefine((values, ctx) => {
  if (!values.user_id && !values.asset_id) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['user_id'], message: 'Selecciona un usuario o un activo' })
  }
})

const almLicenseSchema = z.object({
  name: z.string().trim().min(1, 'El nombre es obligatorio'),
  product_name: z.string().optional(),
  version: z.string().optional(),
  edition: z.string().optional(),
  type: z.enum(['perpetual', 'subscription', 'concurrent', 'named', 'device', 'trial', 'free', 'oem', 'volume']),
  platform: z.enum(['any', 'windows', 'mac', 'linux', 'web', 'mobile']),
  vendor_id: z.union([z.string(), z.number()]).optional(),
  contract_id: z.union([z.string(), z.number()]).optional(),
  total_seats: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().int('Debe ser un entero').min(0, 'No puede ser negativo').optional()),
  license_key: z.string().optional(),
  purchase_date: z.string().optional(),
  expiry_date: z.string().optional(),
  purchase_price: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, 'No puede ser negativo').optional()),
  annual_cost: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, 'No puede ser negativo').optional()),
  cost_center_id: z.union([z.string(), z.number()]).optional(),
  environment: z.enum(['all', 'prod', 'staging', 'dev']),
  is_compliance_req: z.boolean(),
  notes: z.string().optional(),
}).superRefine((values, ctx) => {
  if (values.purchase_date && values.expiry_date && values.expiry_date < values.purchase_date) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['expiry_date'], message: 'La fecha de expiracion no puede ser anterior a la fecha de compra' })
  }
})

const almAssetSchema = z.object({
  name: z.string().trim().min(1, 'El nombre es obligatorio'),
  type: z.enum(['laptop', 'desktop', 'server', 'mobile', 'tablet', 'network', 'printer', 'monitor', 'peripheral', 'vm', 'other']),
  brand: z.string().optional(),
  model: z.string().optional(),
  serial_number: z.string().optional(),
  asset_tag: z.string().optional(),
  status: z.enum(['in_use', 'available', 'in_repair', 'retired', 'lost', 'stolen']),
  condition: z.enum(['new', 'good', 'fair', 'poor']),
  assigned_to_id: z.union([z.string(), z.number()]).optional(),
  location: z.string().optional(),
  vendor_id: z.union([z.string(), z.number()]).optional(),
  purchase_date: z.string().optional(),
  purchase_price: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, 'No puede ser negativo').optional()),
  warranty_expiry: z.string().optional(),
  depreciation_years: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().int('Debe ser un entero').min(0, 'No puede ser negativo').optional()),
  ip_address: z.string().optional(),
  hostname: z.string().optional(),
  os: z.string().optional(),
  cpu: z.string().optional(),
  ram_gb: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, 'No puede ser negativo').optional()),
  storage_gb: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, 'No puede ser negativo').optional()),
  notes: z.string().optional(),
  ci_id: z.string().optional(),
  eol_date: z.string().optional(),
  lease_expiry: z.string().optional(),
  next_maintenance_date: z.string().optional(),
  maintenance_contract: z.string().optional(),
}).superRefine((values, ctx) => {
  if (values.purchase_date && values.warranty_expiry && values.warranty_expiry < values.purchase_date) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['warranty_expiry'], message: 'La garantia no puede terminar antes de la fecha de compra' })
  }
})

function ContractModal({ contract, vendors, users, costCenters, onClose }: { contract: Partial<AlmContract> | null; vendors: Vendor[]; users: UserListItem[]; costCenters: CostCenter[]; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { currency: defaultCurrency } = useOrgSettings()
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
    resolution_hours: contract?.resolution_hours ?? '',
    response_hours: contract?.response_hours ?? '',
    total_value: contract?.total_value || '',
    annual_value: contract?.annual_value || '',
    billing_cycle: contract?.billing_cycle || 'annual',
    currency: contract?.currency || defaultCurrency,
    payment_method: contract?.payment_method || '',
    po_number: contract?.po_number || '',
    cost_center_id: contract?.cost_center_id || '',
    owner_id: contract?.owner_id || '',
    document_url: contract?.document_url || '',
    notes: contract?.notes || '',
    tags: contract?.tags || '',
  })
  const validation = useFormValidation(almContractSchema)
  const s = (k: keyof typeof form) => (e: CambioDeCampo) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }
  const { mutate, isPending } = useMutation({
    mutationFn: (d: DatosValidos<typeof almContractSchema>) => isEdit ? almExtApi.updateContract(contract.id, d) : almExtApi.createContract(d),
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries({ queryKey: ['alm-contracts'] }); qc.invalidateQueries({ queryKey: ['alm-dashboard'] }); onClose() },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate(result.data)
  }
  return (
    <Modal open onClose={onClose} title={isEdit ? t('alm.contracts_modal_edit') : t('alm.contracts_modal_new')} width={720}>
      <div className="u-grid2-14">
        <div className="u-col-full">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('alm.contracts_label_title')} *</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={s('title')} style={validation.inputStyle(fs, 'title')} placeholder={t('alm.contracts_placeholder_title')} />
          {validation.errors.title && <p className="u-field-error">{validation.errors.title}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('alm.contracts_label_vendor')}</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.vendor_id} onChange={s('vendor_id')} style={fs}>
            <option value="">{t('alm.contracts_none_vendor')}</option>
            {vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>{t('alm.contracts_label_type')}</label>
          <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.type} onChange={s('type')} style={fs}>
            {Object.entries(CONTRACT_TYPES).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>{t('alm.contracts_label_status')}</label>
          <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.status} onChange={s('status')} style={fs}>
            {Object.entries(CONTRACT_STATUS).map(([k,v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={ls}>{t('alm.contracts_label_billing_cycle')}</label>
          <select id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.billing_cycle} onChange={s('billing_cycle')} style={fs}>
            {[['one_time',t('alm.contracts_cycle_one_time')],['monthly',t('alm.contracts_cycle_monthly')],['quarterly',t('alm.contracts_cycle_quarterly')],['annual',t('alm.contracts_cycle_annual')],['biennial',t('alm.contracts_cycle_biennial')]].map(([k,l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
        <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={ls}>{t('alm.contracts_label_start_date')}</label><DateInput id={`${idCampo}-6`} value={form.start_date} onChange={s('start_date')} style={validation.inputStyle(fs, 'start_date')} /></div>
        <div>
          <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} style={ls}>{t('alm.contracts_label_end_date')}</label>
          <DateInput id={`${idCampo}-7`} value={form.end_date} onChange={s('end_date')} style={validation.inputStyle(fs, 'end_date')} />
          {validation.errors.end_date && <p className="u-field-error">{validation.errors.end_date}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} style={ls}>{t('alm.contracts_label_renewal_date')}</label>
          <DateInput id={`${idCampo}-8`} value={form.renewal_date} onChange={s('renewal_date')} style={validation.inputStyle(fs, 'renewal_date')} />
          {validation.errors.renewal_date && <p className="u-field-error">{validation.errors.renewal_date}</p>}
        </div>
        <div>
          <label style={ls}>{t('alm.contracts_label_auto_renew')}</label>
          <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
            {[true, false].map(v => (
              <button key={String(v)} onClick={() => setForm(f => ({ ...f, auto_renew: v }))}
                style={{ flex: 1, padding: '8px', borderRadius: 8, border: `1px solid ${form.auto_renew === v ? 'var(--accent)' : 'var(--surface-4)'}`, background: form.auto_renew === v ? 'var(--accent-muted)' : 'transparent', color: form.auto_renew === v ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit' }}>
                {v ? `✅ ${t('alm.contracts_yes')}` : `❌ ${t('alm.contracts_no')}`}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} style={ls}>{t('alm.contracts_label_notice_days')}</label>
          <input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} type="number" value={form.notice_days} onChange={s('notice_days')} style={validation.inputStyle(fs, 'notice_days')} />
          {validation.errors.notice_days && <p className="u-field-error">{validation.errors.notice_days}</p>}
        </div>
        <div>
          <label id="contract-uc-et" style={ls} htmlFor="contract-uc">{t('alm.contracts_label_uc_hours')}</label>
          <input id="contract-uc" aria-labelledby="contract-uc-et" type="number" min={0} step="0.5" value={form.resolution_hours} onChange={s('resolution_hours')} style={validation.inputStyle(fs, 'resolution_hours')} />
          {validation.errors.resolution_hours
            ? <p className="u-field-error">{validation.errors.resolution_hours}</p>
            : <p style={{ marginTop: 4, fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{t('alm.contracts_uc_hint')}</p>}
        </div>
        <div>
          <label id="contract-uc-resp-et" style={ls} htmlFor="contract-uc-resp">{t('alm.contracts_label_uc_response')}</label>
          <input id="contract-uc-resp" aria-labelledby="contract-uc-resp-et" type="number" min={0} step="0.5" value={form.response_hours} onChange={s('response_hours')} style={validation.inputStyle(fs, 'response_hours')} />
          {validation.errors.response_hours && <p className="u-field-error">{validation.errors.response_hours}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et10`} htmlFor={`${idCampo}-10`} style={ls}>{t('alm.contracts_label_total_value')}</label>
          <input id={`${idCampo}-10`} aria-labelledby={`${idCampo}-et10`} type="number" value={form.total_value} onChange={s('total_value')} style={validation.inputStyle(fs, 'total_value')} />
          {validation.errors.total_value && <p className="u-field-error">{validation.errors.total_value}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et11`} htmlFor={`${idCampo}-11`} style={ls}>{t('alm.contracts_label_annual_cost')}</label>
          <input id={`${idCampo}-11`} aria-labelledby={`${idCampo}-et11`} type="number" value={form.annual_value} onChange={s('annual_value')} style={validation.inputStyle(fs, 'annual_value')} />
          {validation.errors.annual_value && <p className="u-field-error">{validation.errors.annual_value}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et12`} htmlFor={`${idCampo}-12`} style={ls}>{t('alm.contracts_label_owner')}</label>
          <select id={`${idCampo}-12`} aria-labelledby={`${idCampo}-et12`} value={form.owner_id} onChange={s('owner_id')} style={fs}>
            <option value="">{t('alm.contracts_none_owner')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et13`} htmlFor={`${idCampo}-13`} style={ls}>{t('alm.contracts_label_cost_center')}</label>
          <select id={`${idCampo}-13`} aria-labelledby={`${idCampo}-et13`} value={form.cost_center_id} onChange={s('cost_center_id')} style={fs}>
            <option value="">{t('alm.contracts_none_cost_center')}</option>
            {costCenters.map(c => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
          </select>
        </div>
        <div><label id={`${idCampo}-et14`} htmlFor={`${idCampo}-14`} style={ls}>{t('alm.contracts_label_po')}</label><input id={`${idCampo}-14`} aria-labelledby={`${idCampo}-et14`} value={form.po_number} onChange={s('po_number')} style={fs} /></div>
        <div><label id={`${idCampo}-et15`} htmlFor={`${idCampo}-15`} style={ls}>{t('alm.contracts_label_payment_method')}</label><input id={`${idCampo}-15`} aria-labelledby={`${idCampo}-et15`} value={form.payment_method} onChange={s('payment_method')} style={fs} placeholder={t('alm.contracts_placeholder_payment_method')} /></div>
        <div className="u-col-full"><label id={`${idCampo}-et16`} htmlFor={`${idCampo}-16`} style={ls}>{t('alm.contracts_label_document_url')}</label><input id={`${idCampo}-16`} aria-labelledby={`${idCampo}-et16`} value={form.document_url} onChange={s('document_url')} style={fs} placeholder={t('alm.contracts_placeholder_document_url')} /></div>
        <div className="u-col-full"><label id={`${idCampo}-et17`} htmlFor={`${idCampo}-17`} style={ls}>{t('alm.contracts_label_notes')}</label><textarea id={`${idCampo}-17`} aria-labelledby={`${idCampo}-et17`} value={form.notes} onChange={s('notes')} rows={3} style={{ ...fs, resize: 'vertical' }} /></div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={submit} disabled={isPending} loading={isPending}>
          {isPending ? t('common.saving') : isEdit ? t('alm.contracts_save_changes') : t('alm.contracts_create')}
        </Button>
      </div>
    </Modal>
  )
}

function ContractsTab() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [modal, setModal] = useState<Partial<AlmContract> | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('active')
  const [urgentOnly, setUrgentOnly] = useState(false)

  const { data: contracts = [], isLoading } = useQuery<AlmContract[]>({ queryKey: ['alm-contracts'], queryFn: () => almExtApi.contracts().then(r => r.data) })
  const { data: vendors = [] } = useQuery<Vendor[]>({ queryKey: ['alm-vendors'], queryFn: () => vendorsApi.list(undefined).then(r => r.data) })
  const { data: users = [] } = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data) })
  const { data: costCenters = [] } = useQuery<CostCenter[]>({ queryKey: ['alm-cost-centers'], queryFn: () => almExtApi.costCenters().then(r => r.data) })

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => almExtApi.deleteContract(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['alm-contracts'] }); qc.invalidateQueries({ queryKey: ['alm-dashboard'] }) },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const filtered = contracts.filter(c =>
    (!search || c.title.toLowerCase().includes(search.toLowerCase()) || c.vendor_name?.toLowerCase().includes(search.toLowerCase())) &&
    (!statusFilter || c.status === statusFilter) &&
    (!urgentOnly || c.renewal_urgent)
  )

  const totalAnnual = filtered.reduce((s: number, c) => s + (c.annual_value || 0), 0)

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input aria-label={t('alm.contracts_search_placeholder')} value={search} onChange={e => setSearch(e.target.value)} placeholder={t('alm.contracts_search_placeholder')}
          style={{ ...fs, flex: 2, minWidth: 200 }} />
        <select aria-label={t('alm.contracts_filter_status_aria')} value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ ...fs, flex: '0 0 160px' }}>
          <option value="">{t('alm.contracts_filter_all_statuses')}</option>
          {Object.entries(CONTRACT_STATUS).map(([k,v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <button aria-pressed={urgentOnly} aria-label={t('alm.contracts_urgent_only_aria')} onClick={() => setUrgentOnly(u => !u)}
          style={{ padding: '8px 14px', borderRadius: 8, border: `1px solid ${urgentOnly ? 'var(--danger-border)' : 'var(--surface-4)'}`, background: urgentOnly ? 'rgba(248,113,113,0.06)' : 'transparent', color: urgentOnly ? 'var(--danger)' : 'var(--text-2)', fontSize: "var(--text-sm)", fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>
          {`⚠️ ${t('alm.contracts_urgent_only')}`}
        </button>
        <Button onClick={() => setModal({})} icon="＋">{t('alm.action_new_contract')}</Button>
      </div>

      {filtered.length > 0 && (
        <div style={{ marginBottom: 16, padding: '10px 16px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, fontSize: "var(--text-base)", color: 'var(--text-2)' }}>
          {filtered.length} contrato(s) · Coste anual total: <strong className="u-warning">{fmtCurrency(totalAnnual)}</strong>
        </div>
      )}

      {isLoading ? <Spinner /> : filtered.length === 0 ? (
        <EmptyState svgIcon={<FileText size={36} />} title={t('alm.no_contracts')} description={t('alm.contracts_empty_desc')} />
      ) : (
        <div className="u-stack-10">
          {filtered.map(c => {
            const _st = CONTRACT_STATUS[c.status] || { label: c.status, color: 'var(--text-2)' }
            const ct = CONTRACT_TYPES[c.type] || { label: c.type, icon: '📄' }
            return (
              <div key={c.id} style={{ ...card, padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 14 }}>
                <div style={{ fontSize: "var(--text-2xl)", flexShrink: 0 }}>{ct.icon}</div>
                <div className="u-flex1-min0">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
                    <span className="u-md-700">{c.title}</span>
                    <StatusBadge status={c.status} cfg={CONTRACT_STATUS} />
                    {c.renewal_urgent && <span style={{ fontSize: "var(--text-xs)", color: 'var(--danger)', fontWeight: 700 }}>⚠️ RENUEVA EN {c.days_to_renewal}d</span>}
                  </div>
                  <div style={{ display: 'flex', gap: 16, fontSize: "var(--text-sm)", color: 'var(--text-2)', flexWrap: 'wrap' }}>
                    {c.vendor_name && <span>🏢 {c.vendor_name}</span>}
                    {c.annual_value && <span>💰 {fmtCurrency(c.annual_value)}{t('alm.ano')}</span>}
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
                  <button aria-label={`Editar contrato ${c.title}`} onClick={() => setModal(c)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '5px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>✏️</button>
                  <button aria-label={`Eliminar contrato ${c.title}`} onClick={() => { openConfirmGlobal({ message: `¿Eliminar el contrato "${c.title}"?`, onConfirm: () => del(c.id), danger: true }) }}
                    style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '5px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>🗑</button>
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
function LicenseAssignModal({ license, onClose }: { license: License; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: users = [] } = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data) })
  const { data: assets = [] } = useQuery<Asset[]>({ queryKey: ['alm-assets'], queryFn: () => assetsApi.list(undefined).then(r => r.data) })
  const [form, setForm] = useState({ user_id: '', asset_id: '', project_id: '', expires_at: '', notes: '' })
  const validation = useFormValidation(almLicenseAssignSchema)
  const s = (k: keyof typeof form) => (e: CambioDeCampo) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }
  const availSeats = license.total_seats ? license.total_seats - (license.used_seats || 0) : null
  const { mutate, isPending } = useMutation({
    mutationFn: (d: DatosValidos<typeof almLicenseAssignSchema>) => licensesApi.assign(license.id, d),
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries({ queryKey: ['alm-licenses'] }); qc.invalidateQueries({ queryKey: ['alm-license', license.id] }); onClose() },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate(result.data)
  }

  return (
    <Modal open onClose={onClose} title={`${t('alm.licenses_assign_title')}: ${license.name}`} width={520}>
      {availSeats !== null && (
        <div style={{ padding: '10px 14px', background: availSeats > 0 ? 'var(--success-bg)' : 'var(--danger-bg)', border: `1px solid ${availSeats > 0 ? 'var(--success-border)' : 'var(--danger-border)'}`, borderRadius: 8, marginBottom: 16, fontSize: "var(--text-base)" }}>
          {availSeats > 0 ? `✅ ${availSeats} ${t('alm.licenses_seats_available')} ${license.total_seats}` : `❌ ${t('alm.licenses_no_seats_available')} (${license.used_seats}/${license.total_seats})`}
        </div>
      )}
      <div className="u-stack-14">
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('alm.licenses_assign_user')}</label>
          <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.user_id} onChange={s('user_id')} style={validation.inputStyle(fs, 'user_id')}>
            <option value="">{t('alm.licenses_none_user')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name} ({u.email})</option>)}
          </select>
          {validation.errors.user_id && <p className="u-field-error">{validation.errors.user_id}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('alm.licenses_assign_device')}</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.asset_id} onChange={s('asset_id')} style={validation.inputStyle(fs, 'asset_id')}>
            <option value="">{t('alm.licenses_none_device')}</option>
            {assets.map(a => <option key={a.id} value={a.id}>{ASSET_TYPES[a.type]?.icon} {a.name} {a.serial_number ? `(${a.serial_number})` : ''}</option>)}
          </select>
        </div>
        <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>{t('alm.licenses_assignment_expiry')}</label><DateInput id={`${idCampo}-3`} value={form.expires_at} onChange={s('expires_at')} style={validation.inputStyle(fs, 'expires_at')} /></div>
        <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>{t('alm.contracts_label_notes')}</label><textarea id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.notes} onChange={s('notes')} rows={2} style={{ ...fs, resize: 'vertical' }} /></div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={submit} disabled={isPending} loading={isPending}>
          {isPending ? t('alm.licenses_assigning') : t('alm.licenses_confirm_assignment')}
        </Button>
      </div>
    </Modal>
  )
}

function LicenseModal({ license, vendors, contracts, costCenters, onClose }: { license: Partial<License> | null; vendors: Vendor[]; contracts: AlmContract[]; costCenters: CostCenter[]; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
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
  const validation = useFormValidation(almLicenseSchema)
  const s = (k: keyof typeof form) => (e: CambioDeCampo) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }
  const { mutate, isPending } = useMutation({
    mutationFn: (d: DatosValidos<typeof almLicenseSchema>) => isEdit ? licensesApi.update(license.id, d) : licensesApi.create(d),
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries({ queryKey: ['alm-licenses'] }); onClose() },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate(result.data)
  }

  return (
    <Modal open onClose={onClose} title={isEdit ? t('alm.licenses_modal_edit') : t('alm.licenses_modal_new')} width={720}>
      <div className="u-grid2-14">
        <div className="u-col-full">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('alm.licenses_label_name')} *</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={s('name')} style={validation.inputStyle(fs, 'name')} placeholder={t('alm.licenses_placeholder_name')} />
          {validation.errors.name && <p className="u-field-error">{validation.errors.name}</p>}
        </div>
        <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('alm.licenses_label_product')}</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.product_name} onChange={s('product_name')} style={fs} placeholder={t('alm.licenses_placeholder_product')} /></div>
        <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>{t('alm.licenses_label_edition')}</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.edition} onChange={s('edition')} style={fs} placeholder={t('alm.licenses_placeholder_edition')} /></div>
        <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>{t('alm.licenses_label_version')}</label><input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.version} onChange={s('version')} style={fs} placeholder={t('alm.licenses_placeholder_version')} /></div>
        <div>
          <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={ls}>{t('alm.licenses_label_type')}</label>
          <select id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.type} onChange={s('type')} style={fs}>
            {Object.entries(LICENSE_TYPES).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={ls}>{t('alm.licenses_label_platform')}</label>
          <select id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.platform} onChange={s('platform')} style={fs}>
            {[['any',t('alm.licenses_platform_all')],['windows','Windows'],['mac','macOS'],['linux','Linux'],['web',t('alm.licenses_platform_web')],['mobile',t('alm.licenses_platform_mobile')]].map(([k,l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} style={ls}>{t('alm.licenses_label_vendor')}</label>
          <select id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.vendor_id} onChange={s('vendor_id')} style={fs}>
            <option value="">{t('alm.licenses_none_vendor')}</option>
            {vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} style={ls}>{t('alm.licenses_label_contract')}</label>
          <select id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} value={form.contract_id} onChange={s('contract_id')} style={fs}>
            <option value="">{t('alm.licenses_none_contract')}</option>
            {contracts.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} style={ls}>{t('alm.licenses_label_total_seats')}</label>
          <input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} type="number" value={form.total_seats} onChange={s('total_seats')} style={validation.inputStyle(fs, 'total_seats')} placeholder="Ej: 50" />
          {validation.errors.total_seats && <p className="u-field-error">{validation.errors.total_seats}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et10`} htmlFor={`${idCampo}-10`} style={ls}>{t('alm.contracts_label_annual_cost')}</label>
          <input id={`${idCampo}-10`} aria-labelledby={`${idCampo}-et10`} type="number" value={form.annual_cost} onChange={s('annual_cost')} style={validation.inputStyle(fs, 'annual_cost')} />
          {validation.errors.annual_cost && <p className="u-field-error">{validation.errors.annual_cost}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et11`} htmlFor={`${idCampo}-11`} style={ls}>{t('alm.assets_label_purchase_price')}</label>
          <input id={`${idCampo}-11`} aria-labelledby={`${idCampo}-et11`} type="number" value={form.purchase_price} onChange={s('purchase_price')} style={validation.inputStyle(fs, 'purchase_price')} />
          {validation.errors.purchase_price && <p className="u-field-error">{validation.errors.purchase_price}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et12`} htmlFor={`${idCampo}-12`} style={ls}>{t('alm.licenses_label_cost_center')}</label>
          <select id={`${idCampo}-12`} aria-labelledby={`${idCampo}-et12`} value={form.cost_center_id} onChange={s('cost_center_id')} style={fs}>
            <option value="">{t('alm.licenses_none_cost_center')}</option>
            {costCenters.map(c => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
          </select>
        </div>
        <div><label id={`${idCampo}-et13`} htmlFor={`${idCampo}-13`} style={ls}>{t('alm.licenses_label_purchase_date')}</label><DateInput id={`${idCampo}-13`} value={form.purchase_date} onChange={s('purchase_date')} style={validation.inputStyle(fs, 'purchase_date')} /></div>
        <div>
          <label id={`${idCampo}-et14`} htmlFor={`${idCampo}-14`} style={ls}>{t('alm.licenses_label_expiry_date')}</label>
          <DateInput id={`${idCampo}-14`} value={form.expiry_date} onChange={s('expiry_date')} style={validation.inputStyle(fs, 'expiry_date')} />
          {validation.errors.expiry_date && <p className="u-field-error">{validation.errors.expiry_date}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et15`} htmlFor={`${idCampo}-15`} style={ls}>{t('alm.licenses_label_environment')}</label>
          <select id={`${idCampo}-15`} aria-labelledby={`${idCampo}-et15`} value={form.environment} onChange={s('environment')} style={fs}>
            {[['all',t('alm.licenses_env_all')],['prod',t('alm.licenses_env_production')],['staging',t('alm.licenses_env_staging')],['dev',t('alm.licenses_env_dev')]].map(([k,l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingTop: 20 }}>
          <input type="checkbox" id="compliance" aria-labelledby="compliance-et" checked={form.is_compliance_req} onChange={e => setForm(f => ({ ...f, is_compliance_req: e.target.checked }))} />
          <label id="compliance-et" htmlFor="compliance" style={{ fontSize: "var(--text-base)", cursor: 'pointer' }}>{t('alm.licenses_requires_compliance')}</label>
        </div>
        <div className="u-col-full"><label id={`${idCampo}-et16`} htmlFor={`${idCampo}-16`} style={ls}>{t('alm.licenses_label_key')}</label><input id={`${idCampo}-16`} aria-labelledby={`${idCampo}-et16`} value={form.license_key} onChange={s('license_key')} style={{ ...fs, fontFamily: 'var(--font-mono)' }} placeholder={t('alm.licenses_placeholder_key')} /></div>
        <div className="u-col-full"><label id={`${idCampo}-et17`} htmlFor={`${idCampo}-17`} style={ls}>{t('alm.contracts_label_notes')}</label><textarea id={`${idCampo}-17`} aria-labelledby={`${idCampo}-et17`} value={form.notes} onChange={s('notes')} rows={3} style={{ ...fs, resize: 'vertical' }} /></div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={submit} disabled={isPending} loading={isPending}>
          {isPending ? t('common.saving') : isEdit ? t('alm.licenses_save') : t('alm.licenses_create')}
        </Button>
      </div>
    </Modal>
  )
}

function LicensesTab() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [modal, setModal] = useState<Partial<License> | null>(null)
  const [assignModal, setAssignModal] = useState<License | null>(null)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const { data: licenses = [], isLoading } = useQuery<License[]>({ queryKey: ['alm-licenses'], queryFn: () => licensesApi.list(undefined).then(r => r.data) })
  const { data: vendors = [] } = useQuery<Vendor[]>({ queryKey: ['alm-vendors'], queryFn: () => vendorsApi.list(undefined).then(r => r.data) })
  const { data: contracts = [] } = useQuery<AlmContract[]>({ queryKey: ['alm-contracts'], queryFn: () => almExtApi.contracts().then(r => r.data) })
  const { data: costCenters = [] } = useQuery<CostCenter[]>({ queryKey: ['alm-cost-centers'], queryFn: () => almExtApi.costCenters().then(r => r.data) })

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => licensesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-licenses'] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const filtered = licenses.filter(l =>
    (!search || l.name.toLowerCase().includes(search.toLowerCase()) || l.vendor_name?.toLowerCase().includes(search.toLowerCase())) &&
    (!typeFilter || l.type === typeFilter) &&
    (!statusFilter || l.status === statusFilter)
  )

  const totalAnnual = filtered.reduce((s: number, l) => s + (l.annual_cost || 0), 0)
  const totalSeats  = filtered.reduce((s: number, l) => s + (l.total_seats || 0), 0)
  const usedSeats   = filtered.reduce((s: number, l) => s + (l.used_seats || 0), 0)

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input aria-label={t('alm.licenses_search_placeholder')} value={search} onChange={e => setSearch(e.target.value)} placeholder={t('alm.licenses_search_placeholder')}
          style={{ ...fs, flex: 2, minWidth: 180 }} />
        <select aria-label={t('alm.licenses_filter_type_aria')} value={typeFilter} onChange={e => setTypeFilter(e.target.value)} style={{ ...fs, flex: '0 0 160px' }}>
          <option value="">{t('alm.licenses_filter_all_types')}</option>
          {Object.entries(LICENSE_TYPES).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
        </select>
        <select aria-label={t('alm.licenses_filter_status_aria')} value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ ...fs, flex: '0 0 160px' }}>
          <option value="">{t('alm.licenses_filter_all_statuses')}</option>
          {Object.entries(LICENSE_STATUS_CFG).map(([k,v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <Button onClick={() => setModal({})} icon="＋">{t('alm.action_register_license')}</Button>
      </div>

      {filtered.length > 0 && (
        <div style={{ marginBottom: 16, padding: '10px 16px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, fontSize: "var(--text-base)", color: 'var(--text-2)', display: 'flex', gap: 20, flexWrap: 'wrap' }}>
          <span>{filtered.length} licencia(s)</span>
          {totalAnnual > 0 && <span>💰 <strong className="u-warning">{fmtCurrency(totalAnnual)}</strong>{t('alm.ano')}</span>}
          {totalSeats > 0 && <span>🔑 {usedSeats}/{totalSeats} seats usados</span>}
        </div>
      )}

      {isLoading ? <Spinner /> : filtered.length === 0 ? (
        <EmptyState svgIcon={<Key size={36} />} title={t('alm.no_licenses')} description={t('alm.licenses_empty_desc')} />
      ) : (
        <div className="u-stack-10">
          {filtered.map(lic => {
            const _st = LICENSE_STATUS_CFG[lic.status] || { label: lic.status, color: 'var(--text-2)' }
            const lt = LICENSE_TYPES[lic.type] || { label: lic.type, icon: '🔑' }
            const pctUsed = lic.total_seats ? (lic.used_seats / lic.total_seats) * 100 : null
            const daysLeft = lic.days_to_expiry
            return (
              <div key={lic.id} style={{ ...card, padding: '16px 20px' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                  <div style={{ fontSize: "var(--text-xl-em)", flexShrink: 0, marginTop: 2 }}>{lt.icon}</div>
                  <div className="u-flex1-min0">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
                      <span className="u-md-700">{lic.name}</span>
                      <StatusBadge status={lic.status} cfg={LICENSE_STATUS_CFG} />
                      {lic.is_compliance_req && <span style={{ fontSize: "var(--text-2xs)", color: 'var(--warning)', border: '1px solid var(--warning-border)', borderRadius: 4, padding: '1px 5px' }}>COMPLIANCE</span>}
                      {daysLeft !== null && daysLeft <= 30 && daysLeft >= 0 && (
                        <span style={{ fontSize: "var(--text-xs)", color: 'var(--danger)', fontWeight: 700 }}>⚠️ Expira en {daysLeft}d</span>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 14, fontSize: "var(--text-sm)", color: 'var(--text-2)', flexWrap: 'wrap', marginBottom: 8 }}>
                      {lic.vendor_name && <span>🏢 {lic.vendor_name}</span>}
                      {lic.annual_cost && <span>💰 {fmtCurrency(lic.annual_cost)}{t('alm.ano')}</span>}
                      {lic.expiry_date && <span>📅 Expira: {fmtDate(lic.expiry_date)}</span>}
                      <span>{lt.label}</span>
                      {lic.linked_clients?.map(cl => (
                        <span key={cl.id} style={{ color: 'var(--accent)', background: 'var(--accent-muted)', padding: '1px 6px', borderRadius: 4 }}>👤 {cl.name}</span>
                      ))}
                      {lic.environment !== 'all' && <span>🌍 {lic.environment}</span>}
                    </div>
                    {lic.total_seats && (
                      <div style={{ marginBottom: 4 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>
                          <span>Seats usados</span>
                          <span style={{ color: (pctUsed ?? 0) > 90 ? 'var(--danger)' : (pctUsed ?? 0) > 75 ? 'var(--warning)' : 'var(--success)', fontWeight: 700 }}>
                            {lic.used_seats}/{lic.total_seats}
                          </span>
                        </div>
                        <div style={{ height: 5, background: 'var(--surface-4)', borderRadius: 3 }}>
                          <div style={{ height: '100%', width: `${Math.min(100, pctUsed ?? 0)}%`, background: (pctUsed ?? 0) > 100 ? 'var(--danger)' : (pctUsed ?? 0) > 75 ? 'var(--warning)' : 'var(--success)', borderRadius: 3 }} />
                        </div>
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                    <button aria-label={`Asignar licencia ${lic.name}`} onClick={() => setAssignModal(lic)}
                      style={{ background: 'none', border: '1px solid var(--accent-border)', borderRadius: 'var(--radius-sm)', padding: '5px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>
                      👤 Asignar
                    </button>
                    <button aria-label={`Editar licencia ${lic.name}`} onClick={() => setModal(lic)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '5px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>✏️</button>
                    <button aria-label={`Eliminar licencia ${lic.name}`} onClick={() => { openConfirmGlobal({ message: `¿Eliminar la licencia "${lic.name}"?`, onConfirm: () => del(lic.id), danger: true }) }}
                      style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '5px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>🗑</button>
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
function AssetModal({ asset, vendors, users, onClose }: { asset: Partial<Asset> | null; vendors: Vendor[]; users: UserListItem[]; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
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
    ci_id: asset?.ci_id || '', eol_date: asset?.eol_date || '', lease_expiry: asset?.lease_expiry || '',
    next_maintenance_date: asset?.next_maintenance_date || '', maintenance_contract: asset?.maintenance_contract || '',
  })
  // Los CIs de la CMDB: el activo físico y el elemento que sostiene.
  const { data: cis = [] } = useQuery<CmdbItem[]>({ queryKey: ['cmdb-items', 'todos'], queryFn: () => cmdbApi.sdList({ page_size: FULL_LIST_SIZE }).then(r => r.data ?? []) })
  const validation = useFormValidation(almAssetSchema)
  const s = (k: keyof typeof form) => (e: CambioDeCampo) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }
  const showNetwork = ['server','vm','network','desktop'].includes(form.type)
  const { mutate, isPending } = useMutation({
    mutationFn: (d: DatosValidos<typeof almAssetSchema>) => isEdit ? assetsApi.update(asset.id, d) : assetsApi.create(d),
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries({ queryKey: ['alm-assets'] }); onClose() },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate(result.data)
  }

  return (
    <Modal open onClose={onClose} title={isEdit ? t('alm.assets_modal_edit') : t('alm.assets_modal_new')} width={720}>
      <div className="u-grid2-14">
        <div className="u-col-full">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('alm.assets_label_name')} *</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={s('name')} style={validation.inputStyle(fs, 'name')} placeholder={t('alm.assets_placeholder_name')} />
          {validation.errors.name && <p className="u-field-error">{validation.errors.name}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('alm.assets_label_type')}</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.type} onChange={s('type')} style={fs}>
            {Object.entries(ASSET_TYPES).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>{t('alm.assets_label_status')}</label>
          <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.status} onChange={s('status')} style={fs}>
            {Object.entries(ASSET_STATUS_CFG).map(([k,v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </div>
        <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>{t('alm.assets_label_brand')}</label><input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.brand} onChange={s('brand')} style={fs} placeholder={t('alm.assets_placeholder_brand')} /></div>
        <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={ls}>{t('alm.assets_label_model')}</label><input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.model} onChange={s('model')} style={fs} /></div>
        <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={ls}>{t('alm.assets_label_serial')}</label><input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.serial_number} onChange={s('serial_number')} style={fs} /></div>
        <div><label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} style={ls}>{t('alm.assets_label_tag')}</label><input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.asset_tag} onChange={s('asset_tag')} style={fs} placeholder={t('alm.assets_placeholder_tag')} /></div>
        <div>
          <label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} style={ls}>{t('alm.assets_label_assigned_to')}</label>
          <select id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} value={form.assigned_to_id} onChange={s('assigned_to_id')} style={fs}>
            <option value="">{t('alm.assets_none_assigned')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
        </div>
        <div><label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} style={ls}>{t('alm.assets_label_location')}</label><input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} value={form.location} onChange={s('location')} style={fs} placeholder={t('alm.assets_placeholder_location')} /></div>
        <div>
          <label id={`${idCampo}-et10`} htmlFor={`${idCampo}-10`} style={ls}>{t('alm.assets_label_vendor')}</label>
          <select id={`${idCampo}-10`} aria-labelledby={`${idCampo}-et10`} value={form.vendor_id} onChange={s('vendor_id')} style={fs}>
            <option value="">{t('alm.assets_none_vendor')}</option>
            {vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et11`} htmlFor={`${idCampo}-11`} style={ls}>{t('alm.assets_label_condition')}</label>
          <select id={`${idCampo}-11`} aria-labelledby={`${idCampo}-et11`} value={form.condition} onChange={s('condition')} style={fs}>
            {[['new',t('alm.assets_condition_new')],['good',t('alm.assets_condition_good')],['fair',t('alm.assets_condition_fair')],['poor',t('alm.assets_condition_poor')]].map(([k,l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
        <div><label id={`${idCampo}-et12`} htmlFor={`${idCampo}-12`} style={ls}>{t('alm.assets_label_purchase_date')}</label><DateInput id={`${idCampo}-12`} value={form.purchase_date} onChange={s('purchase_date')} style={validation.inputStyle(fs, 'purchase_date')} /></div>
        <div>
          <label id={`${idCampo}-et13`} htmlFor={`${idCampo}-13`} style={ls}>{t('alm.assets_label_purchase_price')}</label>
          <input id={`${idCampo}-13`} aria-labelledby={`${idCampo}-et13`} type="number" value={form.purchase_price} onChange={s('purchase_price')} style={validation.inputStyle(fs, 'purchase_price')} />
          {validation.errors.purchase_price && <p className="u-field-error">{validation.errors.purchase_price}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et14`} htmlFor={`${idCampo}-14`} style={ls}>{t('alm.assets_label_warranty_end')}</label>
          <DateInput id={`${idCampo}-14`} value={form.warranty_expiry} onChange={s('warranty_expiry')} style={validation.inputStyle(fs, 'warranty_expiry')} />
          {validation.errors.warranty_expiry && <p className="u-field-error">{validation.errors.warranty_expiry}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et15`} htmlFor={`${idCampo}-15`} style={ls}>{t('alm.assets_label_depreciation_years')}</label>
          <input id={`${idCampo}-15`} aria-labelledby={`${idCampo}-et15`} type="number" value={form.depreciation_years} onChange={s('depreciation_years')} style={validation.inputStyle(fs, 'depreciation_years')} />
          {validation.errors.depreciation_years && <p className="u-field-error">{validation.errors.depreciation_years}</p>}
        </div>
        {showNetwork && <>
          <div><label id={`${idCampo}-et16`} htmlFor={`${idCampo}-16`} style={ls}>{t('alm.assets_label_ip')}</label><input id={`${idCampo}-16`} aria-labelledby={`${idCampo}-et16`} value={form.ip_address} onChange={s('ip_address')} style={fs} placeholder="Ej: 192.168.1.1" /></div>
          <div><label id={`${idCampo}-et17`} htmlFor={`${idCampo}-17`} style={ls}>{t('alm.assets_label_hostname')}</label><input id={`${idCampo}-17`} aria-labelledby={`${idCampo}-et17`} value={form.hostname} onChange={s('hostname')} style={fs} /></div>
          <div><label id={`${idCampo}-et18`} htmlFor={`${idCampo}-18`} style={ls}>{t('alm.assets_label_os')}</label><input id={`${idCampo}-18`} aria-labelledby={`${idCampo}-et18`} value={form.os} onChange={s('os')} style={fs} placeholder={t('alm.assets_placeholder_os')} /></div>
          <div><label id={`${idCampo}-et19`} htmlFor={`${idCampo}-19`} style={ls}>{t('alm.assets_label_cpu')}</label><input id={`${idCampo}-19`} aria-labelledby={`${idCampo}-et19`} value={form.cpu} onChange={s('cpu')} style={fs} placeholder={t('alm.assets_placeholder_cpu')} /></div>
          <div>
            <label id={`${idCampo}-et20`} htmlFor={`${idCampo}-20`} style={ls}>{t('alm.assets_label_ram')}</label>
            <input id={`${idCampo}-20`} aria-labelledby={`${idCampo}-et20`} type="number" value={form.ram_gb} onChange={s('ram_gb')} style={validation.inputStyle(fs, 'ram_gb')} />
            {validation.errors.ram_gb && <p className="u-field-error">{validation.errors.ram_gb}</p>}
          </div>
          <div>
            <label id={`${idCampo}-et21`} htmlFor={`${idCampo}-21`} style={ls}>{t('alm.assets_label_storage')}</label>
            <input id={`${idCampo}-21`} aria-labelledby={`${idCampo}-et21`} type="number" value={form.storage_gb} onChange={s('storage_gb')} style={validation.inputStyle(fs, 'storage_gb')} />
            {validation.errors.storage_gb && <p className="u-field-error">{validation.errors.storage_gb}</p>}
          </div>
        </>}
        <div style={{ gridColumn: '1/-1', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', borderTop: '1px solid var(--surface-4)', paddingTop: 12 }}>
          {t('alm.assets_lifecycle')}
        </div>
        <div className="u-col-full">
          <label style={ls} htmlFor="asset-ci">{t('alm.assets_label_ci')}</label>
          <select id="asset-ci" value={form.ci_id} onChange={s('ci_id')} style={fs}>
            <option value="">{t('alm.assets_none_ci')}</option>
            {cis.map(c => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}
          </select>
          <p style={{ marginTop: 4, fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{t('alm.assets_ci_hint')}</p>
        </div>
        <div><label style={ls} htmlFor="asset-eol">{t('alm.assets_label_eol')}</label><DateInput id="asset-eol" value={form.eol_date} onChange={s('eol_date')} style={fs} /></div>
        <div><label style={ls} htmlFor="asset-lease">{t('alm.assets_label_lease')}</label><DateInput id="asset-lease" value={form.lease_expiry} onChange={s('lease_expiry')} style={fs} /></div>
        <div><label style={ls} htmlFor="asset-maint">{t('alm.assets_label_maintenance')}</label><DateInput id="asset-maint" value={form.next_maintenance_date} onChange={s('next_maintenance_date')} style={fs} /></div>
        <div><label id="asset-maint-c-et" style={ls} htmlFor="asset-maint-c">{t('alm.assets_label_maintenance_contract')}</label><input id="asset-maint-c" aria-labelledby="asset-maint-c-et" value={form.maintenance_contract} onChange={s('maintenance_contract')} style={fs} /></div>
        <div className="u-col-full"><label id={`${idCampo}-et22`} htmlFor={`${idCampo}-22`} style={ls}>{t('alm.assets_label_notes')}</label><textarea id={`${idCampo}-22`} aria-labelledby={`${idCampo}-et22`} value={form.notes} onChange={s('notes')} rows={3} style={{ ...fs, resize: 'vertical' }} /></div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={submit} disabled={isPending} loading={isPending}>
          {isPending ? t('common.saving') : isEdit ? t('alm.licenses_save') : t('alm.assets_create')}
        </Button>
      </div>
    </Modal>
  )
}

const VENCIMIENTO_KEY: Record<string, string> = {
  warranty_expiry: 'alm.expiry_warranty', eol_date: 'alm.expiry_eol',
  lease_expiry: 'alm.expiry_lease', next_maintenance_date: 'alm.expiry_maintenance',
}

function AssetHistoryModal({ asset, onClose }: { asset: Asset; onClose: () => void }) {
  const t = useAppT()
  const { data: filas = [], isLoading } = useQuery<AssetHistoryRow[]>({
    queryKey: ['alm-asset-history', asset.id],
    queryFn: () => assetsApi.history(asset.id).then(r => r.data ?? []),
  })
  return (
    <Modal open onClose={onClose} title={t('alm.assets_history_of', { name: asset.name })} width={560}>
      {isLoading ? <Spinner /> : filas.length === 0 ? (
        <p style={{ color: 'var(--text-2)', textAlign: 'center', padding: 24 }}>{t('alm.assets_history_empty')}</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 460, overflowY: 'auto' }}>
          {filas.map(h => (
            <div key={h.id} style={{ padding: '8px 12px', background: 'var(--surface-1)', borderRadius: 8, fontSize: "var(--text-sm)" }}>
              <div className="u-text2-xs">
                {h.changed_at ? new Date(h.changed_at).toLocaleString(localeActivo()) : ''}{h.user_name ? ` · ${h.user_name}` : ''}{h.note ? ` · ${h.note}` : ''}
              </div>
              <div style={{ wordBreak: 'break-word' }}>
                <code style={{ background: 'var(--surface-3)', padding: '1px 5px', borderRadius: 4 }}>{h.field}</code>{' '}
                {h.old_value ?? '—'} → <strong>{h.new_value ?? '—'}</strong>
              </div>
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}

/** Lo que vence pronto: garantía, fin de vida, leasing o mantenimiento. */
function ExpiringPanel({ assets, onRenew }: { assets: Asset[]; onRenew: (a: Pick<Asset, 'id' | 'name'>) => void }) {
  const t = useAppT()
  const [dias, setDias] = useState(90)
  const { data: filas = [] } = useQuery<ExpiringRow[]>({
    queryKey: ['alm-expiring', dias],
    queryFn: () => assetsApi.expiring(dias).then(r => r.data ?? []),
  })
  return (
    <div style={{ ...card, padding: '14px 18px', marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: filas.length ? 10 : 0 }}>
        <strong style={{ fontSize: "var(--text-base)" }}>{t('alm.expiring_title', { n: filas.length })}</strong>
        <select aria-label={t('alm.expiring_window')} value={dias} onChange={e => setDias(Number(e.target.value))} style={{ ...fs, width: 'auto', padding: '4px 10px' }}>
          {[30, 60, 90, 180].map(d => <option key={d} value={d}>{t('alm.expiring_days', { n: d })}</option>)}
        </select>
      </div>
      {filas.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {filas.map(f => (
            <div key={`${f.asset_id}-${f.expiry_type}`} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: "var(--text-sm)", flexWrap: 'wrap' }}>
              <span style={{ minWidth: 70, fontWeight: 700, color: f.days_remaining <= 7 ? 'var(--danger)' : f.days_remaining <= 30 ? 'var(--warning)' : 'var(--text-2)' }}>
                {t('alm.expiring_in', { n: f.days_remaining })}
              </span>
              <span style={{ flex: 1, minWidth: 160 }}>{f.name} · {t(VENCIMIENTO_KEY[f.expiry_type] ?? f.expiry_type)} {fmtDate(f.expiry_date)}</span>
              {f.refresh_ticket_id
                ? <span className="u-text2-xs">{t('alm.renewal_open')}</span>
                : <Button size="sm" variant="secondary" onClick={() => onRenew(assets.find(a => a.id === f.asset_id) ?? { id: f.asset_id, name: f.name })}>{t('alm.renewal_open_ticket')}</Button>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function AssetsTab() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [modal, setModal] = useState<Partial<Asset> | null>(null)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const { data: assets = [], isLoading } = useQuery<Asset[]>({ queryKey: ['alm-assets'], queryFn: () => assetsApi.list(undefined).then(r => r.data) })
  const { data: vendors = [] } = useQuery<Vendor[]>({ queryKey: ['alm-vendors'], queryFn: () => vendorsApi.list(undefined).then(r => r.data) })
  const { data: users = [] } = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data) })

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => assetsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-assets'] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })
  const [historyOf, setHistoryOf] = useState<Asset | null>(null)
  const { mutate: renovar } = useMutation({
    mutationFn: (a: Pick<Asset, 'id' | 'name'>) => assetsApi.refreshTicket(a.id).then((r): RefreshTicketResult => r.data),
    onSuccess: d => {
      toast.success(t(d.created ? 'alm.renewal_created' : 'alm.renewal_exists', { number: d.number }))
      qc.invalidateQueries({ queryKey: ['alm-assets'] }); qc.invalidateQueries({ queryKey: ['alm-expiring'] })
    },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const filtered = assets.filter(a =>
    (!search || a.name.toLowerCase().includes(search.toLowerCase()) || a.serial_number?.toLowerCase().includes(search.toLowerCase()) || a.asset_tag?.toLowerCase().includes(search.toLowerCase())) &&
    (!typeFilter || a.type === typeFilter) &&
    (!statusFilter || a.status === statusFilter)
  )

  const totalValue     = filtered.reduce((s: number, a) => s + (a.purchase_price || 0), 0)
  const totalBookValue = filtered.reduce((s: number, a) => s + (a.book_value || 0), 0)

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input aria-label={t('alm.assets_search_placeholder')} value={search} onChange={e => setSearch(e.target.value)} placeholder={t('alm.assets_search_placeholder')}
          style={{ ...fs, flex: 2, minWidth: 180 }} />
        <select aria-label={t('alm.assets_filter_type_aria')} value={typeFilter} onChange={e => setTypeFilter(e.target.value)} style={{ ...fs, flex: '0 0 160px' }}>
          <option value="">{t('alm.assets_filter_all_types')}</option>
          {Object.entries(ASSET_TYPES).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
        </select>
        <select aria-label={t('alm.assets_filter_status_aria')} value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ ...fs, flex: '0 0 160px' }}>
          <option value="">{t('alm.assets_filter_all_statuses')}</option>
          {Object.entries(ASSET_STATUS_CFG).map(([k,v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <Button onClick={() => setModal({})} icon="＋">{t('alm.action_add_asset')}</Button>
      </div>

      <ExpiringPanel assets={assets} onRenew={a => renovar(a)} />

      {filtered.length > 0 && (
        <div style={{ marginBottom: 16, padding: '10px 16px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, fontSize: "var(--text-base)", color: 'var(--text-2)', display: 'flex', gap: 20, flexWrap: 'wrap' }}>
          <span>{filtered.length} activo(s)</span>
          {totalValue > 0 && <span>💰 Valor compra: <strong className="u-accent">{fmtCurrency(totalValue)}</strong></span>}
          {totalBookValue > 0 && <span>📊 Valor libros: <strong className="u-success">{fmtCurrency(totalBookValue)}</strong></span>}
        </div>
      )}

      {isLoading ? <Spinner /> : filtered.length === 0 ? (
        <EmptyState svgIcon={<Monitor size={36} />} title={t('alm.no_assets')} description={t('alm.assets_empty_desc')} />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
          {filtered.map(a => {
            const at = ASSET_TYPES[a.type] || ASSET_TYPES.other
            const _st = ASSET_STATUS_CFG[a.status] || { label: a.status, color: 'var(--text-2)' }
            return (
              <div key={a.id} style={{ ...card, padding: '16px 18px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                  <div className="u-row-center-10">
                    <span style={{ fontSize: "var(--text-xl-em)" }}>{at.icon}</span>
                    <div>
                      <div className="u-md-700">{a.name}</div>
                      <div className="u-text2-xs">{a.brand} {a.model}</div>
                    </div>
                  </div>
                  <StatusBadge status={a.status} cfg={ASSET_STATUS_CFG} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3, fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 10 }}>
                  {a.assigned_to_name && <span>👤 {a.assigned_to_name}</span>}
                  {a.location         && <span>📍 {a.location}</span>}
                  {a.serial_number    && <span>🔢 S/N: {a.serial_number}</span>}
                  {a.asset_tag        && <span>🏷️ Tag: {a.asset_tag}</span>}
                  {a.warranty_expiry  && <span style={{ color: a.warranty_expired ? 'var(--danger)' : 'var(--text-2)' }}>{t('alm.garantia')} {fmtDate(a.warranty_expiry)} {a.warranty_expired ? '⚠️' : ''}</span>}
                  {a.purchase_price   && <span>💰 {fmtCurrency(a.purchase_price)} → libros: {fmtCurrency(a.book_value || 0)}</span>}
                  {a.installed_licenses > 0 && <span>📦 {a.installed_licenses} licencia(s) instalada(s)</span>}
                  {a.ci_id && <span>🔗 {t('alm.assets_label_ci')}: {a.ci_code} · {a.ci_name}</span>}
                  {a.eol_date && <span>{t('alm.expiry_eol')}: {fmtDate(a.eol_date)}</span>}
                  {a.lease_expiry && <span>{t('alm.expiry_lease')}: {fmtDate(a.lease_expiry)}</span>}
                  {a.next_maintenance_date && <span>{t('alm.expiry_maintenance')}: {fmtDate(a.next_maintenance_date)}</span>}
                </div>
                <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                  <button aria-label={t('alm.assets_history_of', { name: a.name })} title={t('alm.assets_history')} onClick={() => setHistoryOf(a)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>📋</button>
                  <button aria-label={t('alm.renewal_open_ticket')} title={t('alm.renewal_open_ticket')} onClick={() => renovar(a)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>🔁</button>
                  <button aria-label={`Editar activo ${a.name}`} onClick={() => setModal(a)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>✏️</button>
                  <button aria-label={`Eliminar activo ${a.name}`} onClick={() => { openConfirmGlobal({ message: `¿Eliminar el activo "${a.name}"?`, onConfirm: () => del(a.id), danger: true }) }}
                    style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>🗑</button>
                </div>
              </div>
            )
          })}
        </div>
      )}
      {modal !== null && <AssetModal asset={Object.keys(modal).length ? modal : null} vendors={vendors} users={users} onClose={() => setModal(null)} />}
      {historyOf && <AssetHistoryModal asset={historyOf} onClose={() => setHistoryOf(null)} />}
    </div>
  )
}

// ── Cost Centers ───────────────────────────────────────────────────────────────
function CostCentersTab() {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { currency: defaultCurrency } = useOrgSettings()
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<CostCenter | null>(null)
  const [form, setForm] = useState<CostCenterForm>({ code: '', name: '', description: '', budget_annual: '', currency: defaultCurrency })
  const s = (k: keyof CostCenterForm) => (e: CambioDeCampo) => setForm(f => ({ ...f, [k]: e.target.value }))

  const { data: centers = [], isLoading } = useQuery<CostCenter[]>({ queryKey: ['alm-cost-centers'], queryFn: () => almExtApi.costCenters().then(r => r.data) })

  const { mutate: save, isPending } = useMutation({
    mutationFn: (d: CostCenterForm) => editing ? almExtApi.updateCostCenter(editing.id, d) : almExtApi.createCostCenter(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['alm-cost-centers'] }); setShowForm(false); setEditing(null); setForm({ code: '', name: '', description: '', budget_annual: '', currency: defaultCurrency }) },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id: string) => almExtApi.deleteCostCenter(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-cost-centers'] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const openEdit = (c: CostCenter) => { setEditing(c); setForm({ code: c.code, name: c.name, description: c.description || '', budget_annual: c.budget_annual || '', currency: c.currency || defaultCurrency }); setShowForm(true) }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button onClick={() => { setEditing(null); setShowForm(true) }} icon="＋">{t('alm.action_cost_centers')}</Button>
      </div>
      {showForm && (
        <div style={{ ...card, padding: 20, marginBottom: 20 }}>
          <h4 style={{ margin: '0 0 14px', fontSize: "var(--text-md)", fontWeight: 700 }}>{editing ? t('alm.cost_centers_edit') : t('alm.cost_centers_new')}</h4>
          <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr 120px', gap: 12 }}>
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('alm.cost_centers_label_code')} *</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.code} onChange={s('code')} style={fs} placeholder={t('alm.cost_centers_placeholder_code')} /></div>
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('alm.cost_centers_label_name')} *</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.name} onChange={s('name')} style={fs} placeholder={t('alm.cost_centers_placeholder_name')} /></div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>{t('alm.cost_centers_label_budget')}</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" value={form.budget_annual} onChange={s('budget_annual')} style={fs} /></div>
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>{t('alm.cost_centers_label_currency')}</label><input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.currency} onChange={s('currency')} style={fs} /></div>
            <div className="u-col-full"><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={ls}>{t('alm.cost_centers_label_description')}</label><input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.description} onChange={s('description')} style={fs} /></div>
          </div>
          <div style={{ display: 'flex', gap: 10, marginTop: 14, justifyContent: 'flex-end' }}>
            <Button variant="secondary" onClick={() => { setShowForm(false); setEditing(null) }}>{t('common.cancel')}</Button>
            <Button onClick={() => save(form)} disabled={isPending || !form.code || !form.name} loading={isPending}>{isPending ? t('common.saving') : editing ? t('common.save') : t('alm.cost_centers_new')}</Button>
          </div>
        </div>
      )}
      {isLoading ? <Spinner /> : centers.length === 0 ? (
        <EmptyState svgIcon={<Briefcase size={36} />} title={t('alm.no_cost_centers')} description={t('alm.cost_centers_empty_desc')} />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
          {centers.map(c => (
            <div key={c.id} style={{ ...card, padding: '16px 18px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <div>
                  <span style={{ fontSize: "var(--text-xs)", fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontWeight: 700 }}>{c.code}</span>
                  <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginTop: 2 }}>{c.name}</div>
                </div>
                <div className="u-row-6">
                  <button aria-label={`Editar centro de coste ${c.name}`} onClick={() => openEdit(c)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>✏️</button>
                  <button aria-label={`Eliminar centro de coste ${c.name}`} onClick={() => { openConfirmGlobal({ message: `¿Eliminar el centro de coste "${c.name}"?`, onConfirm: () => del(c.id), danger: true }) }}
                    style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>🗑</button>
                </div>
              </div>
              {c.budget_annual && <div style={{ fontSize: "var(--text-base)", color: 'var(--warning)', fontWeight: 600 }}>{fmtCurrency(c.budget_annual)}{t('alm.ano')}</div>}
              {c.description && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 4 }}>{c.description}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Compliance ─────────────────────────────────────────────────────────────────
function ComplianceTab() {
  const t = useAppT()
  const { data: report = {}, isLoading, refetch } = useQuery<ComplianceReport>({
    queryKey: ['alm-compliance'],
    queryFn: () => almExtApi.compliance().then(r => r.data),
  })
  const issues = report.issues || []

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
        <div>
          <p style={{ color: 'var(--text-2)', fontSize: "var(--text-md)", margin: 0 }}>
            {t('alm.compliance_intro')}
          </p>
        </div>
        <Button onClick={() => refetch()} variant="secondary">{`🔄 ${t('common.refresh')}`}</Button>
      </div>

      {isLoading ? <Spinner /> : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 24 }}>
            <div style={{ ...card, padding: '18px 20px', borderColor: issues.length === 0 ? 'var(--success-border)' : 'var(--danger-border)' }}>
              <div style={{ fontSize: "var(--text-3xl)", marginBottom: 8 }}>{issues.length === 0 ? '✅' : '❌'}</div>
              <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, color: issues.length === 0 ? 'var(--success)' : 'var(--danger)' }}>{issues.length}</div>
              <div className="u-base-600">{t('alm.compliance_issues')}</div>
            </div>
            <div style={{ ...card, padding: '18px 20px' }}>
              <div style={{ fontSize: "var(--text-3xl)", marginBottom: 8 }}>🔴</div>
              <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, color: 'var(--danger)' }}>{report.critical || 0}</div>
              <div className="u-base-600">{t('alm.compliance_critical')}</div>
            </div>
          </div>

          {issues.length === 0 ? (
            <div style={{ ...card, padding: '40px 20px', textAlign: 'center' }}>
              <div className="u-empty-icon">✅</div>
              <div style={{ fontSize: "var(--text-lg)", fontWeight: 700, color: 'var(--success)', marginBottom: 8 }}>{t('alm.compliance_ok')}</div>
              <div className="u-text2-base">{t('alm.compliance_ok_desc')}</div>
            </div>
          ) : (
            <div className="u-stack-10">
              {issues.map((iss, idx) => (
                <div key={idx} style={{ ...card, padding: '14px 18px', borderColor: iss.severity === 'critical' ? 'var(--danger-border)' : 'rgba(245,158,11,0.31)', background: iss.severity === 'critical' ? 'var(--danger-bg)' : 'rgba(245,158,11,0.04)' }}>
                  <div className="u-row-between">
                    <div>
                      <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4 }}>{iss.name}</div>
                      <div className="u-text2-sm">{iss.detail}</div>
                    </div>
                    <div className="u-row-center-8">
                      <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, padding: '2px 9px', borderRadius: 20, background: 'var(--danger-bg)', color: 'var(--danger)', border: '1px solid var(--danger-border)' }}>
                        {iss.issue}
                      </span>
                      <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, padding: '2px 9px', borderRadius: 20, background: iss.severity === 'critical' ? 'var(--danger-bg)' : 'var(--warning-bg)', color: iss.severity === 'critical' ? 'var(--danger)' : 'var(--warning)', border: `1px solid ${iss.severity === 'critical' ? 'rgba(248,113,113,0.25)' : 'rgba(245,158,11,0.25)'}` }}>
                        {iss.severity === 'critical' ? t('alm.compliance_severity_critical') : t('alm.compliance_severity_warning')}
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
export default function ALMPage(): JSX.Element {
  const t = useAppT()
  const [tab, setTab] = useState('dashboard')

  const TABS = [
    { id: 'dashboard',   label: `${t('alm.tab_dashboard')}` },
    { id: 'vendors',     label: `${t('alm.tab_vendors')}` },
    { id: 'contracts',   label: `${t('alm.tab_contracts')}` },
    { id: 'licenses',    label: `${t('alm.tab_licenses')}` },
    { id: 'assets',      label: `${t('alm.tab_assets')}` },
    { id: 'cost',        label: `${t('alm.tab_cost_centers')}` },
    { id: 'compliance',  label: `${t('alm.tab_compliance')}` },
  ]

  return (
    <Page
      icon={<Layers size={18} />}
      title={t('alm.title')}
      subtitle={t('alm.subtitle')}
    >
      {/* Tab bar */}
      <Tabs
        items={TABS}
        active={tab}
        onChange={setTab}
        ariaLabel={t('alm.tablist_aria')}
        style={{ marginBottom: 'var(--space-5)' }}
      />

      {/* Content */}
      {tab === 'dashboard'  && <div id="alm-panel-dashboard" role="tabpanel" aria-labelledby="alm-tab-dashboard"><ALMDashboard onNavigate={setTab} /></div>}
      {tab === 'vendors'    && <div id="alm-panel-vendors" role="tabpanel" aria-labelledby="alm-tab-vendors"><VendorsTab /></div>}
      {tab === 'contracts'  && <div id="alm-panel-contracts" role="tabpanel" aria-labelledby="alm-tab-contracts"><ContractsTab /></div>}
      {tab === 'licenses'   && <div id="alm-panel-licenses" role="tabpanel" aria-labelledby="alm-tab-licenses"><LicensesTab /></div>}
      {tab === 'assets'     && <div id="alm-panel-assets" role="tabpanel" aria-labelledby="alm-tab-assets"><AssetsTab /></div>}
      {tab === 'cost'       && <div id="alm-panel-cost" role="tabpanel" aria-labelledby="alm-tab-cost"><CostCentersTab /></div>}
      {tab === 'compliance' && <div id="alm-panel-compliance" role="tabpanel" aria-labelledby="alm-tab-compliance"><ComplianceTab /></div>}
    </Page>
  )
}
