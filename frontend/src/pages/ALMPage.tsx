import { lazy, Suspense, useEffect, useId, useMemo, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { AxiosResponse } from 'axios'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { z } from 'zod'
import type { ZodType } from 'zod'
import { assetsApi, licensesApi, vendorsApi, almExtApi, usersApi, cmdbApi } from '../services/api'
import type { UserListItem } from '../services/api'
import type { AlmActivo, AlmCentroDeCoste, AlmContrato, AlmKpis, AlmLicencia, AlmProveedor } from '../services/api/tipos-alm'
import type { MetaDeLista } from '../services/api/tipos-plataforma'
import { Button, Spinner, EmptyState, Modal, Tabs, Page, KpiCard, SelectorDePeriodo } from '../components/ui'
import { usePeriodo } from '../hooks/usePeriodo'
import { SIN_HORA } from '../utils/periodo'
import Pagination from '../components/ui/Pagination'
import {
  Layers, Building2, FileText, Key, Monitor, Briefcase, Plus, Pencil, Trash2, AlertTriangle, CheckCircle2,
  XCircle, RefreshCw, User, Mail, Link as LinkIcon, Coins, BarChart3, MapPin, Hash, Tag, Package, Globe,
  CalendarClock, Lightbulb, ShieldAlert, UserPlus, History, FolderKanban, LayoutDashboard, ArrowLeftRight,
  HandCoins, FileSignature, Receipt, Activity, Scale, ChevronRight,
} from 'lucide-react'
import {
  ICONO_ACTIVO, ICONO_CONTRATO, ICONO_LICENCIA, ICONO_LICENCIA_DEFECTO, ICONO_PROVEEDOR, METRICAS,
} from '../components/alm/almFases'
import AsignarModal from '../components/alm/AsignarModal'
import FichaLicencia from '../components/alm/FichaLicencia'
import FichaActivo from '../components/alm/FichaActivo'
import AsignacionesTab, { HistorialPorTitularTab } from './alm/AsignacionesTab'
import CostesTab from './alm/CostesTab'
import RenovacionesTab from './alm/RenovacionesTab'
import ConciliacionTab from './alm/ConciliacionTab'
import ActasTab from './alm/ActasTab'
import { fmtCurrency, fmtDate, extractErr } from '../utils/helpers'
import { sanitizeUrl } from '../utils/security'
import { useAppT } from '../i18n/AppLangContext'
import { useFormValidation } from '../hooks/useFormValidation'
import { useOrgSettings } from '../hooks/useOrgSettings'
import DsBadge from '../components/ui/StatusBadge'
import DateInput from '../components/ui/DateInput'
import { POLL_DEFAULT_MS, SEARCH_DEBOUNCE_MS } from '../constants/timings'
import { FULL_LIST_SIZE, SMALL_PAGE_SIZE } from '../constants/pagination'
import './ALMPage.css'

// ── Constantes ────────────────────────────────────────────────────────────────
// Las etiquetas de cada catálogo se traducen con la clave `alm.<prefijo>_<clave>`
// (p. ej. `alm.vendor_cat_software`); aquí solo quedan icono y color.
type CatalogoIcono = { icon: ReactNode }
type CatalogoColor = { color: string }

const VENDOR_CATS: Record<string, CatalogoIcono & CatalogoColor> = {
  software:   { icon: ICONO_PROVEEDOR.software, color: 'var(--accent)' },
  hardware:   { icon: ICONO_PROVEEDOR.hardware, color: 'var(--purple)' },
  saas:       { icon: ICONO_PROVEEDOR.saas, color: 'var(--success)' },
  cloud:      { icon: ICONO_PROVEEDOR.cloud, color: 'var(--accent)' },
  telecom:    { icon: ICONO_PROVEEDOR.telecom, color: 'var(--warning)' },
  consulting: { icon: ICONO_PROVEEDOR.consulting, color: 'var(--purple)' },
  other:      { icon: ICONO_PROVEEDOR.other, color: 'var(--text-2)' },
}

const CONTRACT_TYPES: Record<string, CatalogoIcono> = Object.fromEntries(
  Object.entries(ICONO_CONTRATO).map(([k, icon]) => [k, { icon }]))

const CONTRACT_STATUS: Record<string, CatalogoColor> = {
  active:    { color: 'var(--success)' },
  expired:   { color: 'var(--danger)' },
  cancelled: { color: 'var(--text-2)' },
  pending:   { color: 'var(--warning)' },
  draft:     { color: 'var(--text-3)' },
}

const LICENSE_TYPES: Record<string, CatalogoIcono> = Object.fromEntries(
  Object.entries(ICONO_LICENCIA).map(([k, icon]) => [k, { icon }]))

const LICENSE_STATUS_CFG: Record<string, CatalogoColor> = {
  active:        { color: 'var(--success)' },
  expired:       { color: 'var(--danger)' },
  unassigned:    { color: 'var(--text-2)' },
  overallocated: { color: 'var(--danger)' },
  cancelled:     { color: 'var(--text-3)' },
}

const ASSET_TYPES: Record<string, CatalogoIcono> = Object.fromEntries(
  Object.entries(ICONO_ACTIVO).map(([k, icon]) => [k, { icon }]))

const ASSET_STATUS_CFG: Record<string, CatalogoColor> = {
  ordered:   { color: 'var(--purple)' },
  available: { color: 'var(--success)' },
  in_use:    { color: 'var(--accent)' },
  on_loan:   { color: 'var(--orange)' },
  in_repair: { color: 'var(--warning)' },
  retired:   { color: 'var(--text-2)' },
  disposed:  { color: 'var(--text-3)' },
  lost:      { color: 'var(--danger)' },
  stolen:    { color: 'var(--danger)' },
}

/** Entorno de una licencia → clave de su etiqueta ('all' no se enseña). */
const ENTORNO_KEY: Record<string, string> = {
  prod: 'alm.licenses_env_production', staging: 'alm.licenses_env_staging', dev: 'alm.licenses_env_dev',
}

/** Filas por página en proveedores, licencias y activos (#22: el backend pagina con page/page_size). */
const ALM_PAGE_SIZE = SMALL_PAGE_SIZE

// ── Entidades (lo que devuelven los endpoints /alm/*: services/api/tipos-alm) ─
type Vendor = AlmProveedor
type AlmContract = AlmContrato
type License = AlmLicencia
type Asset = AlmActivo
type CostCenter = AlmCentroDeCoste
type CostCenterForm = { code: string; name: string; description: string; budget_annual: string | number; currency: string }
type CmdbItem = { id: string; code?: string; name: string }
/** Cambio de un campo de texto, select, textarea o DateInput. */
type CambioDeCampo = { target: { value: string } }
/** Lo que `useFormValidation(esquema)` entrega como datos válidos. */
type DatosValidos<S> = S extends ZodType<infer T> ? T : never

type Traductor = ReturnType<typeof useAppT>

// ── Piezas compartidas (estilos en ALMPage.css) ───────────────────────────────
/** Clase de un campo de formulario: rojo si la validación lo marcó. */
const claseCampo = (error?: string) => (error ? 'alm-input is-invalid' : 'alm-input')

/** Etiqueta traducida de un catálogo; un valor que el catálogo no conoce se enseña tal cual. */
const etiquetaDe = (t: Traductor, prefijo: string, catalogo: Record<string, unknown>, clave: string) =>
  (clave in catalogo ? t(`alm.${prefijo}_${clave}`) : clave)

/** Tono (clase .alm-tone--*) según días que faltan: rojo, ámbar o el de por defecto. */
const tonoPorDias = (dias: number, rojo: number, ambar: number, resto: 'success' | 'muted') =>
  `alm-tone--${dias <= rojo ? 'danger' : dias <= ambar ? 'warning' : resto}`

/** Respuesta paginada de /alm/*: los elementos y el total (meta.total o X-Total-Count). */
type PaginaAlm<T> = { items: T[]; total: number }
function aPagina<T>(r: AxiosResponse<T[]>): PaginaAlm<T> {
  const meta = (r as AxiosResponse<T[]> & { meta?: MetaDeLista }).meta
  const total = meta?.total ?? Number(r.headers?.['x-total-count'] ?? r.data.length)
  return { items: r.data, total }
}

/** El valor tras `ms` sin cambios: la búsqueda va al servidor sin una petición por tecla. */
function useRetardado<T>(valor: T, ms = SEARCH_DEBOUNCE_MS): T {
  const [v, setV] = useState(valor)
  useEffect(() => {
    const id = setTimeout(() => setV(valor), ms)
    return () => clearTimeout(id)
  }, [valor, ms])
  return v
}

/** Si un borrado deja la página actual fuera del total, vuelve a la última que existe. */
function useAjustarPagina(page: number, totalPages: number, setPage: (p: number) => void, listo: boolean) {
  useEffect(() => { if (listo && page > totalPages) setPage(totalPages) }, [listo, page, totalPages, setPage])
}

const StatusBadge = ({ status, cfg, prefijo }: { status: string; cfg: Record<string, CatalogoColor>; prefijo: string }) => {
  const t = useAppT()
  return (
    <DsBadge color={cfg[status]?.color ?? 'var(--text-2)'} caps={false}>{etiquetaDe(t, prefijo, cfg, status)}</DsBadge>
  )
}

/** KPI del kit; si lleva `onClick`, la tarjeta entera abre la pestaña que resume. */
const KPI = ({ icon, label, value, sub, alert, danger, onClick }: { icon: ReactNode; label: ReactNode; value: ReactNode; sub?: ReactNode; alert?: boolean; danger?: boolean; onClick?: () => void }) => {
  const tarjeta = <KpiCard icon={icon} label={label} value={value} sub={sub} warning={!!alert && !danger} danger={!!alert && !!danger} />
  return onClick
    ? <button type="button" onClick={onClick} className="alm-kpi-link">{tarjeta}</button>
    : tarjeta
}

const SectionTitle = ({ children, action }: { children: ReactNode; action?: ReactNode }) => (
  <div className="u-row-between-mb16">
    <h3 className="alm-section-title">{children}</h3>
    {action}
  </div>
)


// ── Dashboard ALM ─────────────────────────────────────────────────────────────
function ALMDashboard({ onNavigate }: { onNavigate: (tab: string) => void }) {
  const t = useAppT()
  const { data: dash, isLoading } = useQuery({
    queryKey: ['alm-dashboard'],
    queryFn: () => almExtApi.dashboard().then(r => r.data),
    refetchInterval: POLL_DEFAULT_MS,
  })
  const kpis: Partial<AlmKpis> = dash?.kpis || {}
  const renewals = dash?.upcoming_renewals || []

  if (isLoading) return <div className="alm-loading"><Spinner size={32} /></div>

  return (
    <div>
      {/* KPIs */}
      <div className="ds-grid-stats alm-kpis">
        <KPI icon={<FileText size={16} />} label={t('alm.dashboard_contracts_active')} value={kpis.total_contracts ?? 0}
          sub={kpis.expiring_soon ? `${kpis.expiring_soon} ${t('alm.dashboard_expire_60')}` : undefined}
          alert={kpis.expiring_soon > 0} />
        <KPI icon={<Key size={16} />} label={t('alm.dashboard_licenses_managed')} value={kpis.total_licenses ?? 0}
          sub={kpis.expired_licenses ? `${kpis.expired_licenses} ${t('alm.dashboard_expired')}` : undefined}
          alert={kpis.expired_licenses > 0} danger />
        <KPI icon={<Monitor size={16} />} label={t('alm.dashboard_assets_inventory')} value={kpis.total_assets ?? 0}
          sub={`${kpis.assets_in_use ?? 0} ${t('alm.dashboard_in_use')}`} />
        <KPI icon={<Building2 size={16} />} label={t('alm.dashboard_vendors_active')} value={kpis.total_vendors ?? 0} />
        <KPI icon={<Coins size={16} />} label={t('alm.dashboard_license_annual_cost')} value={fmtCurrency(kpis.annual_license_cost ?? 0)} sub={t('alm.dashboard_license_cost_scope')} />
        <KPI icon={<BarChart3 size={16} />} label={t('alm.dashboard_total_annual_cost')} value={fmtCurrency(kpis.total_annual_cost ?? 0)} sub={t('alm.dashboard_total_cost_scope')} />
        <KPI icon={<UserPlus size={16} />} label={t('alm.dashboard_pending_approvals')} value={kpis.pending_approvals ?? 0}
          alert={(kpis.pending_approvals ?? 0) > 0} onClick={() => onNavigate('assignments')} />
        <KPI icon={<HandCoins size={16} />} label={t('alm.dashboard_loans_overdue')} value={kpis.loans_overdue ?? 0}
          alert={(kpis.loans_overdue ?? 0) > 0} danger onClick={() => onNavigate('loans')} />
        <KPI icon={<FileSignature size={16} />} label={t('alm.dashboard_acts_pending')} value={kpis.acts_pending_signature ?? 0}
          onClick={() => onNavigate('acts')} />
      </div>

      {/* Renovaciones próximas */}
      <div className="alm-dash-grid">
        <div className="alm-card">
          <div className="alm-dash-panel">
            <SectionTitle action={<Button onClick={() => onNavigate('renewals')} variant="secondary">{t('alm.dashboard_view_renewals')}</Button>}>
              <span className="u-row-center-8"><CalendarClock size={16} aria-hidden="true" />{t('alm.dashboard_upcoming_renewals')}</span>
            </SectionTitle>
            {renewals.length === 0 ? (
              <EmptyState icon={<CheckCircle2 size={28} />} title={t('alm.dashboard_no_urgent_renewals')} description={t('alm.dashboard_no_urgent_renewals_desc')} />
            ) : (
              renewals.map(c => (
                <div key={c.id} className="alm-renewal">
                  <div>
                    <div className="u-base-600">{c.title}</div>
                    <div className="u-text2-xs">{c.vendor_name}</div>
                  </div>
                  <div className="alm-renewal__when">
                    <div className={`alm-renewal__days ${tonoPorDias(c.days_to_renewal, 14, 30, 'success')}`}>
                        {c.days_to_renewal === 0 ? t('alm.dashboard_today') : `${c.days_to_renewal}${t('alm.dashboard_days_short')}`}
                    </div>
                    <div className="u-text2-xs">{fmtDate(c.renewal_date)}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="alm-card">
          <div className="alm-dash-panel">
            <SectionTitle><span className="u-row-center-8"><Lightbulb size={16} aria-hidden="true" />{t('alm.dashboard_quick_actions')}</span></SectionTitle>
            {[
              { icon: <Building2 size={16} />, label: t('alm.action_add_vendor'), tab: 'vendors' },
              { icon: <FileText size={16} />, label: t('alm.action_new_contract'), tab: 'contracts' },
              { icon: <Key size={16} />, label: t('alm.action_register_license'), tab: 'licenses' },
              { icon: <Monitor size={16} />, label: t('alm.action_add_asset'), tab: 'assets' },
              { icon: <CalendarClock size={16} />, label: t('alm.action_renewals'), tab: 'renewals' },
              { icon: <Coins size={16} />, label: t('alm.action_costs'), tab: 'costs' },
              { icon: <Receipt size={16} />, label: t('alm.action_reconciliation'), tab: 'reconciliation' },
              { icon: <Briefcase size={16} />, label: t('alm.action_cost_centers'), tab: 'cost' },
              { icon: <ShieldAlert size={16} />, label: t('alm.action_compliance_report'), tab: 'compliance' },
            ].map(a => (
              <button key={a.tab} type="button" onClick={() => onNavigate(a.tab)} className="alm-quick">
                <span className="alm-quick__icon" aria-hidden="true">{a.icon}</span>
                <span className="alm-quick__label">{a.label}</span>
                <ChevronRight size={14} aria-hidden="true" className="alm-quick__chevron" />
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
    account_number: vendor?.account_number || '', tax_id: '',
    country: vendor?.country || 'ES', notes: vendor?.notes || '',
  })
  const s = (k: keyof typeof form) => (e: CambioDeCampo) => setForm(f => ({ ...f, [k]: e.target.value }))
  const { mutate, isPending } = useMutation({
    // VendorSerializer no envía tax_id: en la edición el campo sale vacío y, si no se
    // escribe, no se manda (antes se mandaba '' y borraba el CIF guardado).
    mutationFn: ({ tax_id, ...resto }: typeof form) => isEdit
      ? vendorsApi.update(vendor.id, tax_id ? { ...resto, tax_id } : resto)
      : vendorsApi.create({ ...resto, tax_id }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['alm-vendors'] }); qc.invalidateQueries({ queryKey: ['alm-dashboard'] }); onClose() },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })
  return (
    <Modal open onClose={onClose} title={isEdit ? t('alm.vendor_modal_edit') : t('alm.vendor_modal_new')} width={640}>
      <div className="u-grid2-14">
        <div className="u-col-full"><label id={`${idPrefix}-name-et`} htmlFor={`${idPrefix}-name`} className="alm-label">{t('alm.vendor_label_name')} *</label><input id={`${idPrefix}-name`} aria-labelledby={`${idPrefix}-name-et`} value={form.name} onChange={s('name')} className="alm-input" placeholder={t('alm.vendor_placeholder_name')} /></div>
        <div>
          <label htmlFor={`${idPrefix}-category`} className="alm-label">{t('alm.vendor_label_category')}</label>
          <select id={`${idPrefix}-category`} value={form.category} onChange={s('category')} className="alm-input">
            {Object.keys(VENDOR_CATS).map(k => <option key={k} value={k}>{t(`alm.vendor_cat_${k}`)}</option>)}
          </select>
        </div>
        <div><label id={`${idPrefix}-country-et`} htmlFor={`${idPrefix}-country`} className="alm-label">{t('alm.vendor_label_country')}</label><input id={`${idPrefix}-country`} aria-labelledby={`${idPrefix}-country-et`} value={form.country} onChange={s('country')} className="alm-input" placeholder={t('alm.ej_espana')} /></div>
        <div><label id={`${idPrefix}-website-et`} htmlFor={`${idPrefix}-website`} className="alm-label">{t('alm.vendor_label_web')}</label><input id={`${idPrefix}-website`} aria-labelledby={`${idPrefix}-website-et`} value={form.website} onChange={s('website')} className="alm-input" placeholder={t('alm.vendor_placeholder_web')} /></div>
        <div><label id={`${idPrefix}-support-email-et`} htmlFor={`${idPrefix}-support-email`} className="alm-label">{t('alm.vendor_label_support_email')}</label><input id={`${idPrefix}-support-email`} aria-labelledby={`${idPrefix}-support-email-et`} value={form.support_email} onChange={s('support_email')} className="alm-input" /></div>
        <div><label id={`${idPrefix}-support-phone-et`} htmlFor={`${idPrefix}-support-phone`} className="alm-label">{t('alm.vendor_label_support_phone')}</label><input id={`${idPrefix}-support-phone`} aria-labelledby={`${idPrefix}-support-phone-et`} value={form.support_phone} onChange={s('support_phone')} className="alm-input" /></div>
        <div><label id={`${idPrefix}-account-manager-et`} htmlFor={`${idPrefix}-account-manager`} className="alm-label">{t('alm.vendor_label_account_manager')}</label><input id={`${idPrefix}-account-manager`} aria-labelledby={`${idPrefix}-account-manager-et`} value={form.account_manager} onChange={s('account_manager')} className="alm-input" /></div>
        <div><label id={`${idPrefix}-account-number-et`} htmlFor={`${idPrefix}-account-number`} className="alm-label">{t('alm.vendor_label_account_number')}</label><input id={`${idPrefix}-account-number`} aria-labelledby={`${idPrefix}-account-number-et`} value={form.account_number} onChange={s('account_number')} className="alm-input" /></div>
        <div><label id={`${idPrefix}-tax-id-et`} htmlFor={`${idPrefix}-tax-id`} className="alm-label">{t('alm.vendor_label_tax_id')}</label><input id={`${idPrefix}-tax-id`} aria-labelledby={`${idPrefix}-tax-id-et`} value={form.tax_id} onChange={s('tax_id')} className="alm-input" /></div>
        <div className="u-col-full"><label id={`${idPrefix}-notes-et`} htmlFor={`${idPrefix}-notes`} className="alm-label">{t('alm.vendor_label_notes')}</label><textarea id={`${idPrefix}-notes`} aria-labelledby={`${idPrefix}-notes-et`} value={form.notes} onChange={s('notes')} rows={3} className="alm-input" /></div>
      </div>
      <div className="alm-modal-actions">
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
  const [page, setPage] = useState(1)
  const q = useRetardado(search.trim())

  // Lista paginada en el servidor: búsqueda (q) y categoría también se filtran allí.
  const { data: pagina, isLoading } = useQuery<PaginaAlm<Vendor>>({
    queryKey: ['alm-vendors', 'pagina', q, catFilter, page],
    queryFn: () => vendorsApi.list({ q: q || undefined, category: catFilter || undefined, page, page_size: ALM_PAGE_SIZE }).then(aPagina),
    placeholderData: keepPreviousData,
  })
  const vendors = pagina?.items ?? []
  const total = pagina?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / ALM_PAGE_SIZE))
  useAjustarPagina(page, totalPages, setPage, !!pagina)
  const { mutate: del } = useMutation({
    mutationFn: (id: string) => vendorsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-vendors'] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  return (
    <div>
      <div className="alm-toolbar alm-toolbar--vendors">
        <input type="search" aria-label={t('alm.vendors_search_placeholder')} value={search} onChange={e => { setSearch(e.target.value); setPage(1) }} placeholder={t('alm.vendors_search_placeholder')}
          className="alm-input alm-toolbar__search" />
        <select aria-label={t('alm.vendors_filter_aria')} value={catFilter} onChange={e => { setCatFilter(e.target.value); setPage(1) }} className="alm-input alm-toolbar__select">
          <option value="">{t('alm.vendors_filter_all_categories')}</option>
          {Object.keys(VENDOR_CATS).map(k => <option key={k} value={k}>{t(`alm.vendor_cat_${k}`)}</option>)}
        </select>
        <Button onClick={() => setModal({})} icon={<Plus size={14} />}>{t('alm.vendors_new')}</Button>
      </div>

      {isLoading ? <Spinner /> : vendors.length === 0 ? (
        <EmptyState svgIcon={<Building2 size={36} />} title={t('alm.vendors_empty_title')} description={t('alm.vendors_empty_desc')} />
      ) : (
        <div className="alm-vendor-grid">
          {vendors.map(v => {
            const catKey = v.category in VENDOR_CATS ? v.category : 'other'
            const cat = VENDOR_CATS[catKey]
            return (
              <div key={v.id} className="alm-card alm-vendor" style={{ '--cat-color': cat.color } as CSSProperties}>
                <div className="alm-vendor__head">
                  <div className="u-row-center-10">
                    <div className="alm-vendor__icon" aria-hidden="true">
                      {cat.icon}
                    </div>
                    <div>
                      <div className="alm-vendor__name">{v.name}</div>
                      <div className="alm-vendor__cat">{t(`alm.vendor_cat_${catKey}`)}</div>
                    </div>
                  </div>
                  <div className="u-row-6">
                    <button type="button" aria-label={t('alm.aria_edit_vendor', { name: v.name })} onClick={() => setModal(v)} className="alm-icon-btn alm-icon-btn--sm"><Pencil size={14} aria-hidden="true" /></button>
                    <button type="button" aria-label={`${t('common.delete')} ${v.name}`} onClick={() => { openConfirmGlobal({ message: `${t('alm.vendors_delete_confirm')} "${v.name}"?`, onConfirm: () => del(v.id), danger: true }) }}
                      className="alm-icon-btn alm-icon-btn--sm alm-icon-btn--danger"><Trash2 size={14} aria-hidden="true" /></button>
                  </div>
                </div>
                <div className="alm-vendor__info">
                  {v.account_manager && <span className="alm-meta-ico"><User size={13} aria-hidden="true" />{v.account_manager}</span>}
                  {v.support_email   && <span className="alm-meta-ico"><Mail size={13} aria-hidden="true" />{v.support_email}</span>}
                  {v.website         && <a href={sanitizeUrl(v.website)} target="_blank" rel="noopener noreferrer" className="alm-vendor__link alm-meta-ico"><LinkIcon size={13} aria-hidden="true" />{v.website}</a>}
                </div>
                <div className="alm-vendor__foot">
                  {v.contracts_count} {t('alm.vendors_contracts_count')}
                </div>
              </div>
            )
          })}
        </div>
      )}
      <div className="alm-pagination">
        <Pagination page={page} totalPages={totalPages} onChange={setPage} total={total} pageSize={ALM_PAGE_SIZE} maxVisible={5} />
      </div>
      {modal !== null && <VendorModal vendor={Object.keys(modal).length ? modal : null} onClose={() => setModal(null)} />}
    </div>
  )
}

// ── Contracts ─────────────────────────────────────────────────────────────────
// Los esquemas se crean con `t` para que los mensajes de error salgan en el idioma activo.
const crearEsquemaContrato = (t: Traductor) => z.object({
  title: z.string().trim().min(1, t('alm.val_title_required')),
  vendor_id: z.union([z.string(), z.number()]).optional(),
  type: z.enum(['purchase', 'subscription', 'maintenance', 'support', 'lease', 'enterprise']),
  status: z.enum(['active', 'expired', 'cancelled', 'pending', 'draft']),
  start_date: z.string().optional(),
  end_date: z.string().optional(),
  renewal_date: z.string().optional(),
  auto_renew: z.boolean(),
  notice_days: z.coerce.number().int(t('alm.val_integer')).min(0, t('alm.val_non_negative')),
  // UC: vacío se envía como null para poder quitar el plazo al editar.
  resolution_hours: z.preprocess((v) => (v === '' || v === undefined ? null : v), z.union([z.null(), z.coerce.number().positive(t('alm.val_hours_positive'))])),
  response_hours: z.preprocess((v) => (v === '' || v === undefined ? null : v), z.union([z.null(), z.coerce.number().positive(t('alm.val_hours_positive'))])),
  total_value: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, t('alm.val_non_negative')).optional()),
  annual_value: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, t('alm.val_non_negative')).optional()),
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
    ctx.addIssue({ code: 'custom', path: ['end_date'], message: t('alm.val_end_before_start') })
  }
  if (values.start_date && values.renewal_date && values.renewal_date < values.start_date) {
    ctx.addIssue({ code: 'custom', path: ['renewal_date'], message: t('alm.val_renewal_before_start') })
  }
})

const crearEsquemaLicencia = (t: Traductor) => z.object({
  name: z.string().trim().min(1, t('alm.val_name_required')),
  product_name: z.string().optional(),
  version: z.string().optional(),
  edition: z.string().optional(),
  type: z.enum(['perpetual', 'subscription', 'concurrent', 'named', 'device', 'trial', 'free', 'oem', 'volume']),
  platform: z.enum(['any', 'windows', 'mac', 'linux', 'web', 'mobile']),
  vendor_id: z.union([z.string(), z.number()]).optional(),
  contract_id: z.union([z.string(), z.number()]).optional(),
  total_seats: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().int(t('alm.val_integer')).min(0, t('alm.val_non_negative')).optional()),
  license_key: z.string().optional(),
  purchase_date: z.string().optional(),
  expiry_date: z.string().optional(),
  purchase_price: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, t('alm.val_non_negative')).optional()),
  annual_cost: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, t('alm.val_non_negative')).optional()),
  cost_center_id: z.union([z.string(), z.number()]).optional(),
  environment: z.enum(['all', 'prod', 'staging', 'dev']),
  is_compliance_req: z.boolean(),
  notes: z.string().optional(),
  metric: z.enum(METRICAS),
  sku: z.string().optional(),
  tier: z.string().optional(),
  tier_rank: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().int(t('alm.val_integer')).min(0, t('alm.val_non_negative')).optional()),
  amortization_months: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().int(t('alm.val_integer')).min(1, t('alm.val_non_negative')).optional()),
  rebillable: z.boolean(),
}).superRefine((values, ctx) => {
  if (values.purchase_date && values.expiry_date && values.expiry_date < values.purchase_date) {
    ctx.addIssue({ code: 'custom', path: ['expiry_date'], message: t('alm.val_expiry_before_purchase') })
  }
})

const crearEsquemaActivo = (t: Traductor) => z.object({
  name: z.string().trim().min(1, t('alm.val_name_required')),
  type: z.enum(['laptop', 'desktop', 'server', 'mobile', 'tablet', 'network', 'printer', 'monitor', 'peripheral', 'vm', 'other']),
  brand: z.string().optional(),
  model: z.string().optional(),
  serial_number: z.string().optional(),
  asset_tag: z.string().optional(),
  status: z.enum(['ordered', 'available', 'in_use', 'on_loan', 'in_repair', 'retired', 'disposed', 'lost', 'stolen']),
  condition: z.enum(['new', 'good', 'fair', 'poor']),
  location: z.string().optional(),
  vendor_id: z.union([z.string(), z.number()]).optional(),
  purchase_date: z.string().optional(),
  purchase_price: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, t('alm.val_non_negative')).optional()),
  warranty_expiry: z.string().optional(),
  depreciation_years: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().int(t('alm.val_integer')).min(0, t('alm.val_non_negative')).optional()),
  ip_address: z.string().optional(),
  hostname: z.string().optional(),
  os: z.string().optional(),
  cpu: z.string().optional(),
  ram_gb: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, t('alm.val_non_negative')).optional()),
  storage_gb: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, t('alm.val_non_negative')).optional()),
  notes: z.string().optional(),
  ci_id: z.string().optional(),
  eol_date: z.string().optional(),
  lease_expiry: z.string().optional(),
  next_maintenance_date: z.string().optional(),
  maintenance_contract: z.string().optional(),
  residual_value: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, t('alm.val_non_negative')).optional()),
  lease_monthly_cost: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, t('alm.val_non_negative')).optional()),
  cost_center_id: z.string().optional(),
  rebillable: z.boolean(),
}).superRefine((values, ctx) => {
  if (values.purchase_date && values.warranty_expiry && values.warranty_expiry < values.purchase_date) {
    ctx.addIssue({ code: 'custom', path: ['warranty_expiry'], message: t('alm.val_warranty_before_purchase') })
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
  const esquema = useMemo(() => crearEsquemaContrato(t), [t])
  const validation = useFormValidation(esquema)
  const s = (k: keyof typeof form) => (e: CambioDeCampo) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }
  const { mutate, isPending } = useMutation({
    mutationFn: (d: DatosValidos<typeof esquema>) => isEdit ? almExtApi.updateContract(contract.id, d) : almExtApi.createContract(d),
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
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="alm-label">{t('alm.contracts_label_title')} *</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={s('title')} className={claseCampo(validation.errors.title)} aria-invalid={!!validation.errors.title} placeholder={t('alm.contracts_placeholder_title')} />
          {validation.errors.title && <p className="u-field-error">{validation.errors.title}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="alm-label">{t('alm.contracts_label_vendor')}</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.vendor_id} onChange={s('vendor_id')} className="alm-input">
            <option value="">{t('alm.contracts_none_vendor')}</option>
            {vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="alm-label">{t('alm.contracts_label_type')}</label>
          <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.type} onChange={s('type')} className="alm-input">
            {Object.entries(CONTRACT_TYPES).map(([k,v]) => <option key={k} value={k}>{v.icon} {t(`alm.contract_type_${k}`)}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="alm-label">{t('alm.contracts_label_status')}</label>
          <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.status} onChange={s('status')} className="alm-input">
            {Object.keys(CONTRACT_STATUS).map(k => <option key={k} value={k}>{t(`alm.contract_status_${k}`)}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="alm-label">{t('alm.contracts_label_billing_cycle')}</label>
          <select id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.billing_cycle} onChange={s('billing_cycle')} className="alm-input">
            {[['one_time',t('alm.contracts_cycle_one_time')],['monthly',t('alm.contracts_cycle_monthly')],['quarterly',t('alm.contracts_cycle_quarterly')],['annual',t('alm.contracts_cycle_annual')],['biennial',t('alm.contracts_cycle_biennial')]].map(([k,l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
        <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="alm-label">{t('alm.contracts_label_start_date')}</label><DateInput id={`${idCampo}-6`} value={form.start_date} onChange={s('start_date')} className={claseCampo(validation.errors.start_date)} aria-invalid={!!validation.errors.start_date} /></div>
        <div>
          <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="alm-label">{t('alm.contracts_label_end_date')}</label>
          <DateInput id={`${idCampo}-7`} value={form.end_date} onChange={s('end_date')} className={claseCampo(validation.errors.end_date)} aria-invalid={!!validation.errors.end_date} />
          {validation.errors.end_date && <p className="u-field-error">{validation.errors.end_date}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} className="alm-label">{t('alm.contracts_label_renewal_date')}</label>
          <DateInput id={`${idCampo}-8`} value={form.renewal_date} onChange={s('renewal_date')} className={claseCampo(validation.errors.renewal_date)} aria-invalid={!!validation.errors.renewal_date} />
          {validation.errors.renewal_date && <p className="u-field-error">{validation.errors.renewal_date}</p>}
        </div>
        <div>
          <span id={`${idCampo}-auto-et`} className="alm-label">{t('alm.contracts_label_auto_renew')}</span>
          <div className="alm-toggle-row" role="group" aria-labelledby={`${idCampo}-auto-et`}>
            {[true, false].map(v => (
              <button key={String(v)} type="button" aria-pressed={form.auto_renew === v} onClick={() => setForm(f => ({ ...f, auto_renew: v }))}
                className="alm-toggle">
                {v ? <><CheckCircle2 size={14} aria-hidden="true" /> {t('alm.contracts_yes')}</> : <><XCircle size={14} aria-hidden="true" /> {t('alm.contracts_no')}</>}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} className="alm-label">{t('alm.contracts_label_notice_days')}</label>
          <input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} type="number" value={form.notice_days} onChange={s('notice_days')} className={claseCampo(validation.errors.notice_days)} aria-invalid={!!validation.errors.notice_days} />
          {validation.errors.notice_days && <p className="u-field-error">{validation.errors.notice_days}</p>}
        </div>
        <div>
          <label id="contract-uc-et" className="alm-label" htmlFor="contract-uc">{t('alm.contracts_label_uc_hours')}</label>
          <input id="contract-uc" aria-labelledby="contract-uc-et" type="number" min={0} step="0.5" value={form.resolution_hours} onChange={s('resolution_hours')} className={claseCampo(validation.errors.resolution_hours)} aria-invalid={!!validation.errors.resolution_hours} />
          {validation.errors.resolution_hours
            ? <p className="u-field-error">{validation.errors.resolution_hours}</p>
            : <p className="alm-hint">{t('alm.contracts_uc_hint')}</p>}
        </div>
        <div>
          <label id="contract-uc-resp-et" className="alm-label" htmlFor="contract-uc-resp">{t('alm.contracts_label_uc_response')}</label>
          <input id="contract-uc-resp" aria-labelledby="contract-uc-resp-et" type="number" min={0} step="0.5" value={form.response_hours} onChange={s('response_hours')} className={claseCampo(validation.errors.response_hours)} aria-invalid={!!validation.errors.response_hours} />
          {validation.errors.response_hours && <p className="u-field-error">{validation.errors.response_hours}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et10`} htmlFor={`${idCampo}-10`} className="alm-label">{t('alm.contracts_label_total_value')}</label>
          <input id={`${idCampo}-10`} aria-labelledby={`${idCampo}-et10`} type="number" value={form.total_value} onChange={s('total_value')} className={claseCampo(validation.errors.total_value)} aria-invalid={!!validation.errors.total_value} />
          {validation.errors.total_value && <p className="u-field-error">{validation.errors.total_value}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et11`} htmlFor={`${idCampo}-11`} className="alm-label">{t('alm.contracts_label_annual_cost')}</label>
          <input id={`${idCampo}-11`} aria-labelledby={`${idCampo}-et11`} type="number" value={form.annual_value} onChange={s('annual_value')} className={claseCampo(validation.errors.annual_value)} aria-invalid={!!validation.errors.annual_value} />
          {validation.errors.annual_value && <p className="u-field-error">{validation.errors.annual_value}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et12`} htmlFor={`${idCampo}-12`} className="alm-label">{t('alm.contracts_label_owner')}</label>
          <select id={`${idCampo}-12`} aria-labelledby={`${idCampo}-et12`} value={form.owner_id} onChange={s('owner_id')} className="alm-input">
            <option value="">{t('alm.contracts_none_owner')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et13`} htmlFor={`${idCampo}-13`} className="alm-label">{t('alm.contracts_label_cost_center')}</label>
          <select id={`${idCampo}-13`} aria-labelledby={`${idCampo}-et13`} value={form.cost_center_id} onChange={s('cost_center_id')} className="alm-input">
            <option value="">{t('alm.contracts_none_cost_center')}</option>
            {costCenters.map(c => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
          </select>
        </div>
        <div><label id={`${idCampo}-et14`} htmlFor={`${idCampo}-14`} className="alm-label">{t('alm.contracts_label_po')}</label><input id={`${idCampo}-14`} aria-labelledby={`${idCampo}-et14`} value={form.po_number} onChange={s('po_number')} className="alm-input" /></div>
        <div><label id={`${idCampo}-et15`} htmlFor={`${idCampo}-15`} className="alm-label">{t('alm.contracts_label_payment_method')}</label><input id={`${idCampo}-15`} aria-labelledby={`${idCampo}-et15`} value={form.payment_method} onChange={s('payment_method')} className="alm-input" placeholder={t('alm.contracts_placeholder_payment_method')} /></div>
        <div className="u-col-full"><label id={`${idCampo}-et16`} htmlFor={`${idCampo}-16`} className="alm-label">{t('alm.contracts_label_document_url')}</label><input id={`${idCampo}-16`} aria-labelledby={`${idCampo}-et16`} value={form.document_url} onChange={s('document_url')} className="alm-input" placeholder={t('alm.contracts_placeholder_document_url')} /></div>
        <div className="u-col-full"><label id={`${idCampo}-et17`} htmlFor={`${idCampo}-17`} className="alm-label">{t('alm.contracts_label_notes')}</label><textarea id={`${idCampo}-17`} aria-labelledby={`${idCampo}-et17`} value={form.notes} onChange={s('notes')} rows={3} className="alm-input" /></div>
      </div>
      <div className="alm-modal-actions">
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
  const [page, setPage] = useState(1)

  // Todo se filtra y pagina en el servidor: estado, texto (q: título, referencia y
  // proveedor) y renovación urgente. El texto va con retardo para no pedir por tecla.
  const q = useRetardado(search.trim())
  const { data: pagina, isLoading } = useQuery<PaginaAlm<AlmContract>>({
    queryKey: ['alm-contracts', 'pagina', statusFilter, q, urgentOnly, page],
    queryFn: () => almExtApi.contracts({
      status: statusFilter || undefined,
      q: q || undefined,
      renewal_urgent: urgentOnly || undefined,
      page, page_size: ALM_PAGE_SIZE,
    }).then(aPagina),
    placeholderData: keepPreviousData,
  })
  const { data: vendors = [] } = useQuery<Vendor[]>({ queryKey: ['alm-vendors'], queryFn: () => vendorsApi.list(undefined).then(r => r.data) })
  const { data: users = [] } = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data) })
  const { data: costCenters = [] } = useQuery<CostCenter[]>({ queryKey: ['alm-cost-centers'], queryFn: () => almExtApi.costCenters().then(r => r.data) })

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => almExtApi.deleteContract(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['alm-contracts'] }); qc.invalidateQueries({ queryKey: ['alm-dashboard'] }) },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const visibles = pagina?.items ?? []
  const total = pagina?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / ALM_PAGE_SIZE))
  useAjustarPagina(page, totalPages, setPage, !!pagina)
  // Solo se conoce la página: el importe se rotula así cuando hay más de una.
  const sumaDePagina = totalPages > 1
  const totalAnnual = visibles.reduce((s: number, c) => s + (c.annual_value || 0), 0)

  return (
    <div>
      <div className="alm-toolbar">
        <input type="search" aria-label={t('alm.contracts_search_placeholder')} value={search} onChange={e => { setSearch(e.target.value); setPage(1) }} placeholder={t('alm.contracts_search_placeholder')}
          className="alm-input alm-toolbar__search alm-toolbar__search--wide" />
        <select aria-label={t('alm.contracts_filter_status_aria')} value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1) }} className="alm-input alm-toolbar__select--fixed">
          <option value="">{t('alm.contracts_filter_all_statuses')}</option>
          {Object.keys(CONTRACT_STATUS).map(k => <option key={k} value={k}>{t(`alm.contract_status_${k}`)}</option>)}
        </select>
        <button type="button" aria-pressed={urgentOnly} aria-label={t('alm.contracts_urgent_only_aria')} onClick={() => { setUrgentOnly(u => !u); setPage(1) }}
          className="alm-urgent">
          <AlertTriangle size={14} aria-hidden="true" /> {t('alm.contracts_urgent_only')}
        </button>
        <Button onClick={() => setModal({})} icon={<Plus size={14} />}>{t('alm.action_new_contract')}</Button>
      </div>

      {visibles.length > 0 && (
        <div className="alm-summary">
          {t('alm.contracts_count', { n: total })} · {t('alm.contracts_total_annual')} <strong className="u-warning">{fmtCurrency(totalAnnual)}</strong>
          {sumaDePagina && <> <span className="u-text3">{t('alm.summary_this_page')}</span></>}
        </div>
      )}

      {isLoading ? <Spinner /> : visibles.length === 0 ? (
        <EmptyState svgIcon={<FileText size={36} />} title={t('alm.no_contracts')} description={t('alm.contracts_empty_desc')} />
      ) : (
        <div className="u-stack-10">
          {visibles.map(c => {
            return (
              <div key={c.id} className="alm-card alm-row-item">
                <div className="alm-row-item__icon" aria-hidden="true">{CONTRACT_TYPES[c.type]?.icon ?? <FileText size={16} />}</div>
                <div className="u-flex1-min0">
                  <div className="alm-row-item__title">
                    <span className="u-md-700">{c.title}</span>
                    <StatusBadge status={c.status} cfg={CONTRACT_STATUS} prefijo="contract_status" />
                    {c.renewal_urgent && <span className="alm-flag alm-meta-ico"><AlertTriangle size={12} aria-hidden="true" />{t('alm.contracts_renews_in', { n: c.days_to_renewal })}</span>}
                  </div>
                  <div className="alm-row-item__meta">
                    {c.vendor_name && <span className="alm-meta-ico"><Building2 size={13} aria-hidden="true" />{c.vendor_name}</span>}
                    {c.annual_value && <span className="alm-meta-ico"><Coins size={13} aria-hidden="true" />{fmtCurrency(c.annual_value)}{t('alm.ano')}</span>}
                    {c.renewal_date && <span className="alm-meta-ico"><RefreshCw size={13} aria-hidden="true" />{t('alm.contracts_renew_on', { date: fmtDate(c.renewal_date) })}</span>}
                    {c.auto_renew && <span>{t('alm.auto_renew')}</span>}
                    {c.owner_name && <span className="alm-meta-ico"><User size={13} aria-hidden="true" />{c.owner_name}</span>}
                    {c.linked_clients?.map(cl => (
                      <span key={cl.id} className="alm-client-chip alm-meta-ico"><Briefcase size={12} aria-hidden="true" />{cl.name}</span>
                    ))}
                    <span>{etiquetaDe(t, 'contract_type', CONTRACT_TYPES, c.type)}</span>
                    <span>{t('alm.licenses_count', { n: c.licenses_count })}</span>
                  </div>
                </div>
                <div className="alm-actions">
                  <button type="button" aria-label={t('alm.aria_edit_contract', { name: c.title })} onClick={() => setModal(c)} className="alm-icon-btn"><Pencil size={15} aria-hidden="true" /></button>
                  <button type="button" aria-label={t('alm.aria_delete_contract', { name: c.title })} onClick={() => { openConfirmGlobal({ message: t('alm.contracts_delete_confirm_named', { name: c.title }), onConfirm: () => del(c.id), danger: true }) }}
                    className="alm-icon-btn alm-icon-btn--danger"><Trash2 size={15} aria-hidden="true" /></button>
                </div>
              </div>
            )
          })}
        </div>
      )}
      <div className="alm-pagination">
        <Pagination page={page} totalPages={totalPages} onChange={setPage} total={total} pageSize={ALM_PAGE_SIZE} maxVisible={5} />
      </div>
      {modal !== null && <ContractModal contract={Object.keys(modal).length ? modal : null} vendors={vendors} users={users} costCenters={costCenters} onClose={() => setModal(null)} />}
    </div>
  )
}

// ── Licenses ───────────────────────────────────────────────────────────────────
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
    metric: license?.metric || 'named_user', sku: license?.sku || '', tier: license?.tier || '',
    tier_rank: license?.tier_rank ?? '', amortization_months: license?.amortization_months ?? '',
    rebillable: license?.rebillable ?? false,
  })
  const esquema = useMemo(() => crearEsquemaLicencia(t), [t])
  const validation = useFormValidation(esquema)
  const s = (k: keyof typeof form) => (e: CambioDeCampo) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }
  const { mutate, isPending } = useMutation({
    mutationFn: (d: DatosValidos<typeof esquema>) => isEdit ? licensesApi.update(license.id, d) : licensesApi.create(d),
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
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="alm-label">{t('alm.licenses_label_name')} *</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={s('name')} className={claseCampo(validation.errors.name)} aria-invalid={!!validation.errors.name} placeholder={t('alm.licenses_placeholder_name')} />
          {validation.errors.name && <p className="u-field-error">{validation.errors.name}</p>}
        </div>
        <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="alm-label">{t('alm.licenses_label_product')}</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.product_name} onChange={s('product_name')} className="alm-input" placeholder={t('alm.licenses_placeholder_product')} /></div>
        <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="alm-label">{t('alm.licenses_label_edition')}</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.edition} onChange={s('edition')} className="alm-input" placeholder={t('alm.licenses_placeholder_edition')} /></div>
        <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="alm-label">{t('alm.licenses_label_version')}</label><input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.version} onChange={s('version')} className="alm-input" placeholder={t('alm.licenses_placeholder_version')} /></div>
        <div>
          <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="alm-label">{t('alm.licenses_label_type')}</label>
          <select id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.type} onChange={s('type')} className="alm-input">
            {Object.keys(LICENSE_TYPES).map(k => <option key={k} value={k}>{t(`alm.license_type_${k}`)}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor={`${idCampo}-metric`} className="alm-label">{t('alm.metric')}</label>
          <select id={`${idCampo}-metric`} value={form.metric} onChange={s('metric')} className="alm-input">
            {METRICAS.map(k => <option key={k} value={k}>{t(`alm.metric_${k}`)}</option>)}
          </select>
          <p className="alm-hint">{t(`alm.metric_${form.metric}_hint`)}</p>
        </div>
        <div>
          <label htmlFor={`${idCampo}-tier`} className="alm-label">{t('alm.tier')}</label>
          <input id={`${idCampo}-tier`} value={form.tier} onChange={s('tier')} className="alm-input" placeholder={t('alm.tier_placeholder')} />
        </div>
        <div>
          <label htmlFor={`${idCampo}-tierrank`} className="alm-label">{t('alm.tier_rank')}</label>
          <input id={`${idCampo}-tierrank`} type="number" min={0} value={form.tier_rank} onChange={s('tier_rank')} className={claseCampo(validation.errors.tier_rank)} />
          <p className="alm-hint">{t('alm.tier_rank_hint')}</p>
        </div>
        <div>
          <label htmlFor={`${idCampo}-sku`} className="alm-label">{t('alm.sku')}</label>
          <input id={`${idCampo}-sku`} value={form.sku} onChange={s('sku')} className="alm-input" />
        </div>
        <div>
          <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="alm-label">{t('alm.licenses_label_platform')}</label>
          <select id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.platform} onChange={s('platform')} className="alm-input">
            {[['any',t('alm.licenses_platform_all')],['windows','Windows'],['mac','macOS'],['linux','Linux'],['web',t('alm.licenses_platform_web')],['mobile',t('alm.licenses_platform_mobile')]].map(([k,l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="alm-label">{t('alm.licenses_label_vendor')}</label>
          <select id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.vendor_id} onChange={s('vendor_id')} className="alm-input">
            <option value="">{t('alm.licenses_none_vendor')}</option>
            {vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} className="alm-label">{t('alm.licenses_label_contract')}</label>
          <select id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} value={form.contract_id} onChange={s('contract_id')} className="alm-input">
            <option value="">{t('alm.licenses_none_contract')}</option>
            {contracts.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} className="alm-label">{t('alm.licenses_label_total_seats')}</label>
          <input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} type="number" value={form.total_seats} onChange={s('total_seats')} className={claseCampo(validation.errors.total_seats)} aria-invalid={!!validation.errors.total_seats} placeholder={t('alm.licenses_placeholder_seats')} />
          {validation.errors.total_seats && <p className="u-field-error">{validation.errors.total_seats}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et10`} htmlFor={`${idCampo}-10`} className="alm-label">{t('alm.contracts_label_annual_cost')}</label>
          <input id={`${idCampo}-10`} aria-labelledby={`${idCampo}-et10`} type="number" value={form.annual_cost} onChange={s('annual_cost')} className={claseCampo(validation.errors.annual_cost)} aria-invalid={!!validation.errors.annual_cost} />
          {validation.errors.annual_cost && <p className="u-field-error">{validation.errors.annual_cost}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et11`} htmlFor={`${idCampo}-11`} className="alm-label">{t('alm.assets_label_purchase_price')}</label>
          <input id={`${idCampo}-11`} aria-labelledby={`${idCampo}-et11`} type="number" value={form.purchase_price} onChange={s('purchase_price')} className={claseCampo(validation.errors.purchase_price)} aria-invalid={!!validation.errors.purchase_price} />
          {validation.errors.purchase_price && <p className="u-field-error">{validation.errors.purchase_price}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et12`} htmlFor={`${idCampo}-12`} className="alm-label">{t('alm.licenses_label_cost_center')}</label>
          <select id={`${idCampo}-12`} aria-labelledby={`${idCampo}-et12`} value={form.cost_center_id} onChange={s('cost_center_id')} className="alm-input">
            <option value="">{t('alm.licenses_none_cost_center')}</option>
            {costCenters.map(c => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
          </select>
        </div>
        <div><label id={`${idCampo}-et13`} htmlFor={`${idCampo}-13`} className="alm-label">{t('alm.licenses_label_purchase_date')}</label><DateInput id={`${idCampo}-13`} value={form.purchase_date} onChange={s('purchase_date')} className={claseCampo(validation.errors.purchase_date)} aria-invalid={!!validation.errors.purchase_date} /></div>
        <div>
          <label id={`${idCampo}-et14`} htmlFor={`${idCampo}-14`} className="alm-label">{t('alm.licenses_label_expiry_date')}</label>
          <DateInput id={`${idCampo}-14`} value={form.expiry_date} onChange={s('expiry_date')} className={claseCampo(validation.errors.expiry_date)} aria-invalid={!!validation.errors.expiry_date} />
          {validation.errors.expiry_date && <p className="u-field-error">{validation.errors.expiry_date}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et15`} htmlFor={`${idCampo}-15`} className="alm-label">{t('alm.licenses_label_environment')}</label>
          <select id={`${idCampo}-15`} aria-labelledby={`${idCampo}-et15`} value={form.environment} onChange={s('environment')} className="alm-input">
            {[['all',t('alm.licenses_env_all')],['prod',t('alm.licenses_env_production')],['staging',t('alm.licenses_env_staging')],['dev',t('alm.licenses_env_dev')]].map(([k,l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor={`${idCampo}-amort`} className="alm-label">{t('alm.amortization_months')}</label>
          <input id={`${idCampo}-amort`} type="number" min={1} value={form.amortization_months} onChange={s('amortization_months')} className={claseCampo(validation.errors.amortization_months)} />
          <p className="alm-hint">{t('alm.amortization_months_hint')}</p>
        </div>
        <div className="alm-check-row">
          <input type="checkbox" id={`${idCampo}-compliance`} checked={form.is_compliance_req} onChange={e => setForm(f => ({ ...f, is_compliance_req: e.target.checked }))} />
          <label htmlFor={`${idCampo}-compliance`} className="alm-check-label">{t('alm.licenses_requires_compliance')}</label>
        </div>
        <div className="alm-check-row">
          <input type="checkbox" id={`${idCampo}-rebill`} checked={form.rebillable} onChange={e => setForm(f => ({ ...f, rebillable: e.target.checked }))} />
          <label htmlFor={`${idCampo}-rebill`} className="alm-check-label">{t('alm.rebillable_default')}</label>
        </div>
        <div className="u-col-full">
          <label htmlFor={`${idCampo}-16`} className="alm-label">{t('alm.licenses_label_key')}</label>
          <input id={`${idCampo}-16`} value={form.license_key} onChange={s('license_key')} className="alm-input alm-input--mono" autoComplete="off"
            placeholder={license?.has_key ? t('alm.key_keep', { hint: license.license_key_hint ?? '' }) : t('alm.licenses_placeholder_key')} />
          <p className="alm-hint">{t('alm.key_encrypted_hint')}</p>
        </div>
        <div className="u-col-full"><label id={`${idCampo}-et17`} htmlFor={`${idCampo}-17`} className="alm-label">{t('alm.contracts_label_notes')}</label><textarea id={`${idCampo}-17`} aria-labelledby={`${idCampo}-et17`} value={form.notes} onChange={s('notes')} rows={3} className="alm-input" /></div>
      </div>
      <div className="alm-modal-actions">
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
  const [ficha, setFicha] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)
  const q = useRetardado(search.trim().toLowerCase())

  // Estado, texto (q: nombre y proveedor) y tipo se filtran y paginan en el servidor.
  const { data: pagina, isLoading } = useQuery<PaginaAlm<License>>({
    queryKey: ['alm-licenses', 'pagina', statusFilter, q, typeFilter, page],
    queryFn: () => licensesApi.list({
      status: statusFilter || undefined,
      q: q || undefined,
      type: typeFilter || undefined,
      page, page_size: ALM_PAGE_SIZE,
    }).then(aPagina),
    placeholderData: keepPreviousData,
  })
  const { data: vendors = [] } = useQuery<Vendor[]>({ queryKey: ['alm-vendors'], queryFn: () => vendorsApi.list(undefined).then(r => r.data) })
  const { data: contracts = [] } = useQuery<AlmContract[]>({ queryKey: ['alm-contracts'], queryFn: () => almExtApi.contracts().then(r => r.data) })
  const { data: costCenters = [] } = useQuery<CostCenter[]>({ queryKey: ['alm-cost-centers'], queryFn: () => almExtApi.costCenters().then(r => r.data) })

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => licensesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-licenses'] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const visibles = pagina?.items ?? []
  const total = pagina?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / ALM_PAGE_SIZE))
  useAjustarPagina(page, totalPages, setPage, !!pagina)
  // Solo se conoce la página: los importes se rotulan así cuando hay más de una.
  const sumaDePagina = totalPages > 1

  const totalAnnual = visibles.reduce((s: number, l) => s + (l.annual_cost || 0), 0)
  const totalSeats  = visibles.reduce((s: number, l) => s + (l.total_seats || 0), 0)
  const usedSeats   = visibles.reduce((s: number, l) => s + (l.used_seats || 0), 0)

  return (
    <div>
      <div className="alm-toolbar">
        <input type="search" aria-label={t('alm.licenses_search_placeholder')} value={search} onChange={e => { setSearch(e.target.value); setPage(1) }} placeholder={t('alm.licenses_search_placeholder')}
          className="alm-input alm-toolbar__search" />
        <select aria-label={t('alm.licenses_filter_type_aria')} value={typeFilter} onChange={e => { setTypeFilter(e.target.value); setPage(1) }} className="alm-input alm-toolbar__select--fixed">
          <option value="">{t('alm.licenses_filter_all_types')}</option>
          {Object.keys(LICENSE_TYPES).map(k => <option key={k} value={k}>{t(`alm.license_type_${k}`)}</option>)}
        </select>
        <select aria-label={t('alm.licenses_filter_status_aria')} value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1) }} className="alm-input alm-toolbar__select--fixed">
          <option value="">{t('alm.licenses_filter_all_statuses')}</option>
          {Object.keys(LICENSE_STATUS_CFG).map(k => <option key={k} value={k}>{t(`alm.license_status_${k}`)}</option>)}
        </select>
        <Button onClick={() => setModal({})} icon={<Plus size={14} />}>{t('alm.action_register_license')}</Button>
      </div>

      {visibles.length > 0 && (
        <div className="alm-summary alm-summary--row">
          <span>{t('alm.licenses_count', { n: total })}</span>
          {totalAnnual > 0 && <span className="alm-meta-ico"><Coins size={13} aria-hidden="true" /><strong className="u-warning">{fmtCurrency(totalAnnual)}</strong>{t('alm.ano')}</span>}
          {totalSeats > 0 && <span className="alm-meta-ico"><Key size={13} aria-hidden="true" />{t('alm.licenses_seats_used_of', { used: usedSeats, total: totalSeats })}</span>}
          {sumaDePagina && (totalAnnual > 0 || totalSeats > 0) && <span className="u-text3">{t('alm.summary_this_page')}</span>}
        </div>
      )}

      {isLoading ? <Spinner /> : visibles.length === 0 ? (
        <EmptyState svgIcon={<Key size={36} />} title={t('alm.no_licenses')} description={t('alm.licenses_empty_desc')} />
      ) : (
        <div className="u-stack-10">
          {visibles.map(lic => {
            const ocupados = lic.metric === 'concurrent' ? (lic.concurrent_peak ?? 0) : lic.used_seats
            const pctUsed = lic.total_seats ? (ocupados / lic.total_seats) * 100 : 0
            const tonoUso = `alm-tone--${pctUsed > 90 ? 'danger' : pctUsed > 75 ? 'warning' : 'success'}`
            const tonoBarra = `alm-tone--${pctUsed > 100 ? 'danger' : pctUsed > 75 ? 'warning' : 'success'}`
            const daysLeft = lic.days_to_expiry
            return (
              <div key={lic.id} className="alm-card alm-license">
                <div className="alm-license__body">
                  <div className="alm-license__icon" aria-hidden="true">{LICENSE_TYPES[lic.type]?.icon ?? ICONO_LICENCIA_DEFECTO}</div>
                  <div className="u-flex1-min0">
                    <div className="alm-row-item__title">
                      <button type="button" className="alm-link-btn u-md-700" onClick={() => setFicha(lic.id)}>{lic.name}</button>
                      <StatusBadge status={lic.status} cfg={LICENSE_STATUS_CFG} prefijo="license_status" />
                      {lic.tier && <span className="alm-compliance-tag">{lic.tier}</span>}
                      {lic.pending_count > 0 && <span className="alm-flag">{t('alm.pending_n', { n: lic.pending_count })}</span>}
                      {lic.is_compliance_req && <span className="alm-compliance-tag">{t('alm.compliance_badge')}</span>}
                      {daysLeft !== null && daysLeft <= 30 && daysLeft >= 0 && (
                        <span className="alm-flag alm-meta-ico"><AlertTriangle size={12} aria-hidden="true" />{t('alm.licenses_expires_in', { n: daysLeft })}</span>
                      )}
                    </div>
                    <div className="alm-row-item__meta">
                      {lic.vendor_name && <span className="alm-meta-ico"><Building2 size={13} aria-hidden="true" />{lic.vendor_name}</span>}
                      {lic.annual_cost && <span className="alm-meta-ico"><Coins size={13} aria-hidden="true" />{fmtCurrency(lic.annual_cost)}{t('alm.ano')}</span>}
                      {lic.expiry_date && <span className="alm-meta-ico"><CalendarClock size={13} aria-hidden="true" />{t('alm.licenses_expires_on', { date: fmtDate(lic.expiry_date) })}</span>}
                      <span>{etiquetaDe(t, 'license_type', LICENSE_TYPES, lic.type)}</span>
                      <span>{t(`alm.metric_${lic.metric}`)}</span>
                      {lic.linked_clients?.map(cl => (
                        <span key={cl.id} className="alm-client-chip alm-meta-ico"><Briefcase size={12} aria-hidden="true" />{cl.name}</span>
                      ))}
                      {lic.environment !== 'all' && <span className="alm-meta-ico"><Globe size={13} aria-hidden="true" />{ENTORNO_KEY[lic.environment] ? t(ENTORNO_KEY[lic.environment]) : lic.environment}</span>}
                    </div>
                    {lic.total_seats && (
                      <div className="alm-seats">
                        <div className="alm-seats__head">
                          <span>{lic.metric === 'concurrent' ? t('alm.seats_peak') : t('alm.licenses_seats_used')}</span>
                          <span className={`alm-seats__count ${tonoUso}`}>
                            {ocupados}/{lic.total_seats}
                          </span>
                        </div>
                        <div className="alm-seats__track" role="progressbar" aria-label={t('alm.licenses_seats_used')}
                          aria-valuemin={0} aria-valuemax={lic.total_seats} aria-valuenow={ocupados}>
                          <div className={`alm-seats__fill ${tonoBarra}`} style={{ '--pct': `${Math.min(100, pctUsed)}%` } as CSSProperties} />
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="alm-actions">
                    <button type="button" aria-label={t('alm.aria_assign_license', { name: lic.name })} onClick={() => setAssignModal(lic)}
                      className="alm-icon-btn alm-icon-btn--accent alm-meta-ico">
                      <UserPlus size={14} aria-hidden="true" />{t('alm.licenses_assign')}
                    </button>
                    <button type="button" aria-label={t('alm.aria_detail', { name: lic.name })} onClick={() => setFicha(lic.id)} className="alm-icon-btn"><History size={15} aria-hidden="true" /></button>
                    <button type="button" aria-label={t('alm.aria_edit_license', { name: lic.name })} onClick={() => setModal(lic)} className="alm-icon-btn"><Pencil size={15} aria-hidden="true" /></button>
                    <button type="button" aria-label={t('alm.aria_delete_license', { name: lic.name })} onClick={() => { openConfirmGlobal({ message: t('alm.licenses_delete_confirm', { name: lic.name }), onConfirm: () => del(lic.id), danger: true }) }}
                      className="alm-icon-btn alm-icon-btn--danger"><Trash2 size={15} aria-hidden="true" /></button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
      <div className="alm-pagination">
        <Pagination page={page} totalPages={totalPages} onChange={setPage} total={total} pageSize={ALM_PAGE_SIZE} maxVisible={5} />
      </div>
      {modal !== null && <LicenseModal license={Object.keys(modal).length ? modal : null} vendors={vendors} contracts={contracts} costCenters={costCenters} onClose={() => setModal(null)} />}
      {assignModal && <AsignarModal onClose={() => setAssignModal(null)}
        recurso={{ tipo: 'license', id: assignModal.id, nombre: assignModal.name, metric: assignModal.metric, totalSeats: assignModal.total_seats, usedSeats: assignModal.used_seats }} />}
      {ficha && <FichaLicencia licenseId={ficha} onClose={() => setFicha(null)} />}
    </div>
  )
}

// ── Assets ─────────────────────────────────────────────────────────────────────
function AssetModal({ asset, vendors, onClose }: { asset: Partial<Asset> | null; vendors: Vendor[]; onClose: () => void }) {
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
    location: asset?.location || '',
    vendor_id: asset?.vendor_id || '',
    purchase_date: asset?.purchase_date || '', purchase_price: asset?.purchase_price || '',
    warranty_expiry: asset?.warranty_expiry || '', depreciation_years: asset?.depreciation_years || 3,
    ip_address: asset?.ip_address || '', hostname: asset?.hostname || '',
    os: asset?.os || '', cpu: asset?.cpu || '', ram_gb: asset?.ram_gb || '', storage_gb: asset?.storage_gb || '',
    notes: asset?.notes || '',
    ci_id: asset?.ci_id || '', eol_date: asset?.eol_date || '', lease_expiry: asset?.lease_expiry || '',
    next_maintenance_date: asset?.next_maintenance_date || '', maintenance_contract: asset?.maintenance_contract || '',
    residual_value: asset?.residual_value ?? '', lease_monthly_cost: asset?.lease_monthly_cost ?? '',
    cost_center_id: asset?.cost_center_id || '', rebillable: asset?.rebillable ?? false,
  })
  const { data: costCenters = [] } = useQuery<CostCenter[]>({ queryKey: ['alm-cost-centers'], queryFn: () => almExtApi.costCenters().then(r => r.data) })
  // El estado cambia con las acciones del ciclo de vida; aquí solo «comprado» o «en almacén».
  const estadoEditable = !isEdit || ['ordered', 'available'].includes(form.status)
  // Los CIs de la CMDB: el activo físico y el elemento que sostiene.
  const { data: cis = [] } = useQuery<CmdbItem[]>({ queryKey: ['cmdb-items', 'todos'], queryFn: () => cmdbApi.sdList({ page_size: FULL_LIST_SIZE }).then(r => r.data ?? []) })
  const esquema = useMemo(() => crearEsquemaActivo(t), [t])
  const validation = useFormValidation(esquema)
  const s = (k: keyof typeof form) => (e: CambioDeCampo) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }
  const showNetwork = ['server','vm','network','desktop'].includes(form.type)
  const { mutate, isPending } = useMutation({
    mutationFn: (d: DatosValidos<typeof esquema>) => isEdit ? assetsApi.update(asset.id, d) : assetsApi.create(d),
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
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="alm-label">{t('alm.assets_label_name')} *</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={s('name')} className={claseCampo(validation.errors.name)} aria-invalid={!!validation.errors.name} placeholder={t('alm.assets_placeholder_name')} />
          {validation.errors.name && <p className="u-field-error">{validation.errors.name}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="alm-label">{t('alm.assets_label_type')}</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.type} onChange={s('type')} className="alm-input">
            {Object.keys(ASSET_TYPES).map(k => <option key={k} value={k}>{t(`alm.asset_type_${k}`)}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="alm-label">{t('alm.assets_label_status')}</label>
          {estadoEditable ? (
            <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.status} onChange={s('status')} className="alm-input">
              {['ordered', 'available'].map(k => <option key={k} value={k}>{t(`alm.asset_status_${k}`)}</option>)}
            </select>
          ) : (
            <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={t(`alm.asset_status_${form.status}`)} readOnly className="alm-input" />
          )}
          <p className="alm-hint">{t('alm.status_by_actions_hint')}</p>
        </div>
        <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="alm-label">{t('alm.assets_label_brand')}</label><input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.brand} onChange={s('brand')} className="alm-input" placeholder={t('alm.assets_placeholder_brand')} /></div>
        <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="alm-label">{t('alm.assets_label_model')}</label><input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.model} onChange={s('model')} className="alm-input" /></div>
        <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="alm-label">{t('alm.assets_label_serial')}</label><input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.serial_number} onChange={s('serial_number')} className="alm-input" /></div>
        <div><label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="alm-label">{t('alm.assets_label_tag')}</label><input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.asset_tag} onChange={s('asset_tag')} className="alm-input" placeholder={t('alm.assets_placeholder_tag')} /></div>
        <div>
          <label htmlFor={`${idCampo}-cc`} className="alm-label">{t('alm.licenses_label_cost_center')}</label>
          <select id={`${idCampo}-cc`} value={form.cost_center_id} onChange={s('cost_center_id')} className="alm-input">
            <option value="">{t('alm.licenses_none_cost_center')}</option>
            {costCenters.map(c => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}
          </select>
        </div>
        <div><label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} className="alm-label">{t('alm.assets_label_location')}</label><input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} value={form.location} onChange={s('location')} className="alm-input" placeholder={t('alm.assets_placeholder_location')} /></div>
        <div>
          <label id={`${idCampo}-et10`} htmlFor={`${idCampo}-10`} className="alm-label">{t('alm.assets_label_vendor')}</label>
          <select id={`${idCampo}-10`} aria-labelledby={`${idCampo}-et10`} value={form.vendor_id} onChange={s('vendor_id')} className="alm-input">
            <option value="">{t('alm.assets_none_vendor')}</option>
            {vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et11`} htmlFor={`${idCampo}-11`} className="alm-label">{t('alm.assets_label_condition')}</label>
          <select id={`${idCampo}-11`} aria-labelledby={`${idCampo}-et11`} value={form.condition} onChange={s('condition')} className="alm-input">
            {[['new',t('alm.assets_condition_new')],['good',t('alm.assets_condition_good')],['fair',t('alm.assets_condition_fair')],['poor',t('alm.assets_condition_poor')]].map(([k,l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
        <div><label id={`${idCampo}-et12`} htmlFor={`${idCampo}-12`} className="alm-label">{t('alm.assets_label_purchase_date')}</label><DateInput id={`${idCampo}-12`} value={form.purchase_date} onChange={s('purchase_date')} className={claseCampo(validation.errors.purchase_date)} aria-invalid={!!validation.errors.purchase_date} /></div>
        <div>
          <label id={`${idCampo}-et13`} htmlFor={`${idCampo}-13`} className="alm-label">{t('alm.assets_label_purchase_price')}</label>
          <input id={`${idCampo}-13`} aria-labelledby={`${idCampo}-et13`} type="number" value={form.purchase_price} onChange={s('purchase_price')} className={claseCampo(validation.errors.purchase_price)} aria-invalid={!!validation.errors.purchase_price} />
          {validation.errors.purchase_price && <p className="u-field-error">{validation.errors.purchase_price}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et14`} htmlFor={`${idCampo}-14`} className="alm-label">{t('alm.assets_label_warranty_end')}</label>
          <DateInput id={`${idCampo}-14`} value={form.warranty_expiry} onChange={s('warranty_expiry')} className={claseCampo(validation.errors.warranty_expiry)} aria-invalid={!!validation.errors.warranty_expiry} />
          {validation.errors.warranty_expiry && <p className="u-field-error">{validation.errors.warranty_expiry}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et15`} htmlFor={`${idCampo}-15`} className="alm-label">{t('alm.assets_label_depreciation_years')}</label>
          <input id={`${idCampo}-15`} aria-labelledby={`${idCampo}-et15`} type="number" value={form.depreciation_years} onChange={s('depreciation_years')} className={claseCampo(validation.errors.depreciation_years)} aria-invalid={!!validation.errors.depreciation_years} />
          {validation.errors.depreciation_years && <p className="u-field-error">{validation.errors.depreciation_years}</p>}
        </div>
        <div>
          <label htmlFor={`${idCampo}-res`} className="alm-label">{t('alm.residual_value')}</label>
          <input id={`${idCampo}-res`} type="number" min={0} value={form.residual_value} onChange={s('residual_value')} className={claseCampo(validation.errors.residual_value)} />
        </div>
        <div>
          <label htmlFor={`${idCampo}-lease`} className="alm-label">{t('alm.lease_monthly_cost')}</label>
          <input id={`${idCampo}-lease`} type="number" min={0} value={form.lease_monthly_cost} onChange={s('lease_monthly_cost')} className={claseCampo(validation.errors.lease_monthly_cost)} />
        </div>
        <div className="alm-check-row">
          <input type="checkbox" id={`${idCampo}-rebill`} checked={form.rebillable} onChange={e => setForm(f => ({ ...f, rebillable: e.target.checked }))} />
          <label htmlFor={`${idCampo}-rebill`} className="alm-check-label">{t('alm.rebillable_default')}</label>
        </div>
        {showNetwork && <>
          <div><label id={`${idCampo}-et16`} htmlFor={`${idCampo}-16`} className="alm-label">{t('alm.assets_label_ip')}</label><input id={`${idCampo}-16`} aria-labelledby={`${idCampo}-et16`} value={form.ip_address} onChange={s('ip_address')} className="alm-input" placeholder={t('alm.assets_placeholder_ip')} /></div>
          <div><label id={`${idCampo}-et17`} htmlFor={`${idCampo}-17`} className="alm-label">{t('alm.assets_label_hostname')}</label><input id={`${idCampo}-17`} aria-labelledby={`${idCampo}-et17`} value={form.hostname} onChange={s('hostname')} className="alm-input" /></div>
          <div><label id={`${idCampo}-et18`} htmlFor={`${idCampo}-18`} className="alm-label">{t('alm.assets_label_os')}</label><input id={`${idCampo}-18`} aria-labelledby={`${idCampo}-et18`} value={form.os} onChange={s('os')} className="alm-input" placeholder={t('alm.assets_placeholder_os')} /></div>
          <div><label id={`${idCampo}-et19`} htmlFor={`${idCampo}-19`} className="alm-label">{t('alm.assets_label_cpu')}</label><input id={`${idCampo}-19`} aria-labelledby={`${idCampo}-et19`} value={form.cpu} onChange={s('cpu')} className="alm-input" placeholder={t('alm.assets_placeholder_cpu')} /></div>
          <div>
            <label id={`${idCampo}-et20`} htmlFor={`${idCampo}-20`} className="alm-label">{t('alm.assets_label_ram')}</label>
            <input id={`${idCampo}-20`} aria-labelledby={`${idCampo}-et20`} type="number" value={form.ram_gb} onChange={s('ram_gb')} className={claseCampo(validation.errors.ram_gb)} aria-invalid={!!validation.errors.ram_gb} />
            {validation.errors.ram_gb && <p className="u-field-error">{validation.errors.ram_gb}</p>}
          </div>
          <div>
            <label id={`${idCampo}-et21`} htmlFor={`${idCampo}-21`} className="alm-label">{t('alm.assets_label_storage')}</label>
            <input id={`${idCampo}-21`} aria-labelledby={`${idCampo}-et21`} type="number" value={form.storage_gb} onChange={s('storage_gb')} className={claseCampo(validation.errors.storage_gb)} aria-invalid={!!validation.errors.storage_gb} />
            {validation.errors.storage_gb && <p className="u-field-error">{validation.errors.storage_gb}</p>}
          </div>
        </>}
        <div className="alm-subhead">
          {t('alm.assets_lifecycle')}
        </div>
        <div className="u-col-full">
          <label className="alm-label" htmlFor="asset-ci">{t('alm.assets_label_ci')}</label>
          <select id="asset-ci" value={form.ci_id} onChange={s('ci_id')} className="alm-input">
            <option value="">{t('alm.assets_none_ci')}</option>
            {cis.map(c => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}
          </select>
          <p className="alm-hint">{t('alm.assets_ci_hint')}</p>
        </div>
        <div><label className="alm-label" htmlFor="asset-eol">{t('alm.assets_label_eol')}</label><DateInput id="asset-eol" value={form.eol_date} onChange={s('eol_date')} className="alm-input" /></div>
        <div><label className="alm-label" htmlFor="asset-lease">{t('alm.assets_label_lease')}</label><DateInput id="asset-lease" value={form.lease_expiry} onChange={s('lease_expiry')} className="alm-input" /></div>
        <div><label className="alm-label" htmlFor="asset-maint">{t('alm.assets_label_maintenance')}</label><DateInput id="asset-maint" value={form.next_maintenance_date} onChange={s('next_maintenance_date')} className="alm-input" /></div>
        <div><label id="asset-maint-c-et" className="alm-label" htmlFor="asset-maint-c">{t('alm.assets_label_maintenance_contract')}</label><input id="asset-maint-c" aria-labelledby="asset-maint-c-et" value={form.maintenance_contract} onChange={s('maintenance_contract')} className="alm-input" /></div>
        <div className="u-col-full"><label id={`${idCampo}-et22`} htmlFor={`${idCampo}-22`} className="alm-label">{t('alm.assets_label_notes')}</label><textarea id={`${idCampo}-22`} aria-labelledby={`${idCampo}-et22`} value={form.notes} onChange={s('notes')} rows={3} className="alm-input" /></div>
      </div>
      <div className="alm-modal-actions">
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

/** Lo que vence pronto: garantía, fin de vida, leasing o mantenimiento. */
function ExpiringPanel({ assets, onRenew }: { assets: Asset[]; onRenew: (a: Pick<Asset, 'id' | 'name'>) => void }) {
  const t = useAppT()
  // Periodo libre (16-11-2026): horizonte hacia delante; las fechas de vencimiento son de calendario (sin hora).
  const periodo = usePeriodo({ sentido: 'futuro', defecto: 'prox90d', granularidades: SIN_HORA, prefijo: 'venc_' })
  const { data: filas = [] } = useQuery({
    queryKey: ['alm-expiring', periodo.params],
    queryFn: () => assetsApi.expiring({ ...periodo.params }).then(r => r.data),
  })
  return (
    <div className="alm-card alm-expiring">
      <div className={`alm-expiring__head${filas.length ? ' alm-expiring__head--spaced' : ''}`}>
        <strong className="alm-expiring__title">{t('alm.expiring_title', { n: filas.length })}</strong>
        <SelectorDePeriodo {...periodo.selector} sinGranularidad />
      </div>
      {filas.length > 0 && (
        <div className="alm-expiring__list">
          {filas.map(f => (
            <div key={`${f.asset_id}-${f.expiry_type}`} className="alm-expiring__row">
              <span className={`alm-expiring__days ${tonoPorDias(f.days_remaining, 7, 30, 'muted')}`}>
                {t('alm.expiring_in', { n: f.days_remaining })}
              </span>
              <span className="alm-expiring__what">{f.name} · {t(VENCIMIENTO_KEY[f.expiry_type] ?? f.expiry_type)} {fmtDate(f.expiry_date)}</span>
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
  const [page, setPage] = useState(1)
  const q = useRetardado(search.trim())

  // Lista paginada en el servidor: q busca en nombre, nº de serie, etiqueta y hostname.
  const { data: pagina, isLoading } = useQuery<PaginaAlm<Asset>>({
    queryKey: ['alm-assets', 'pagina', q, typeFilter, statusFilter, page],
    queryFn: () => assetsApi.list({
      q: q || undefined, type: typeFilter || undefined, status: statusFilter || undefined, page, page_size: ALM_PAGE_SIZE,
    }).then(aPagina),
    placeholderData: keepPreviousData,
  })
  const assets = pagina?.items ?? []
  const total = pagina?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / ALM_PAGE_SIZE))
  useAjustarPagina(page, totalPages, setPage, !!pagina)
  const { data: vendors = [] } = useQuery<Vendor[]>({ queryKey: ['alm-vendors'], queryFn: () => vendorsApi.list(undefined).then(r => r.data) })
  const { mutate: del } = useMutation({
    mutationFn: (id: string) => assetsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-assets'] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })
  const [ficha, setFicha] = useState<string | null>(null)
  const { mutate: renovar } = useMutation({
    mutationFn: (a: Pick<Asset, 'id' | 'name'>) => assetsApi.refreshTicket(a.id).then(r => r.data),
    onSuccess: d => {
      toast.success(t(d.created ? 'alm.renewal_created' : 'alm.renewal_exists', { number: d.number }))
      qc.invalidateQueries({ queryKey: ['alm-assets'] }); qc.invalidateQueries({ queryKey: ['alm-expiring'] })
    },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  // Importes de la página que se ve (el servidor no devuelve sumas).
  const totalValue     = assets.reduce((s: number, a) => s + (a.purchase_price || 0), 0)
  const totalBookValue = assets.reduce((s: number, a) => s + (a.book_value || 0), 0)

  return (
    <div>
      <div className="alm-toolbar">
        <input type="search" aria-label={t('alm.assets_search_placeholder')} value={search} onChange={e => { setSearch(e.target.value); setPage(1) }} placeholder={t('alm.assets_search_placeholder')}
          className="alm-input alm-toolbar__search" />
        <select aria-label={t('alm.assets_filter_type_aria')} value={typeFilter} onChange={e => { setTypeFilter(e.target.value); setPage(1) }} className="alm-input alm-toolbar__select--fixed">
          <option value="">{t('alm.assets_filter_all_types')}</option>
          {Object.entries(ASSET_TYPES).map(([k,v]) => <option key={k} value={k}>{v.icon} {t(`alm.asset_type_${k}`)}</option>)}
        </select>
        <select aria-label={t('alm.assets_filter_status_aria')} value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1) }} className="alm-input alm-toolbar__select--fixed">
          <option value="">{t('alm.assets_filter_all_statuses')}</option>
          {Object.keys(ASSET_STATUS_CFG).map(k => <option key={k} value={k}>{t(`alm.asset_status_${k}`)}</option>)}
        </select>
        <Button onClick={() => setModal({})} icon={<Plus size={14} />}>{t('alm.action_add_asset')}</Button>
      </div>

      <ExpiringPanel assets={assets} onRenew={a => renovar(a)} />

      {assets.length > 0 && (
        <div className="alm-summary alm-summary--row">
          <span>{t('alm.assets_count', { n: total })}</span>
          {totalValue > 0 && <span className="alm-meta-ico"><Coins size={13} aria-hidden="true" />{t('alm.assets_purchase_value')} <strong className="u-accent">{fmtCurrency(totalValue)}</strong></span>}
          {totalBookValue > 0 && <span className="alm-meta-ico"><BarChart3 size={13} aria-hidden="true" />{t('alm.assets_book_value')} <strong className="u-success">{fmtCurrency(totalBookValue)}</strong></span>}
          {totalPages > 1 && (totalValue > 0 || totalBookValue > 0) && <span className="u-text3">{t('alm.summary_this_page')}</span>}
        </div>
      )}

      {isLoading ? <Spinner /> : assets.length === 0 ? (
        <EmptyState svgIcon={<Monitor size={36} />} title={t('alm.no_assets')} description={t('alm.assets_empty_desc')} />
      ) : (
        <div className="alm-asset-grid">
          {assets.map(a => {
            const at = ASSET_TYPES[a.type] || ASSET_TYPES.other
            return (
              <div key={a.id} className="alm-card alm-asset">
                <div className="alm-asset__head">
                  <div className="u-row-center-10">
                    <span className="alm-asset__icon" aria-hidden="true">{at.icon}</span>
                    <div>
                      <button type="button" className="alm-link-btn u-md-700" onClick={() => setFicha(a.id)}>{a.name}</button>
                      <div className="u-text2-xs">{a.brand} {a.model}</div>
                    </div>
                  </div>
                  <span className="u-row-6">
                    <StatusBadge status={a.status} cfg={ASSET_STATUS_CFG} prefijo="asset_status" />
                    {a.loan_overdue && <span className="alm-flag">{t('alm.st_overdue')}</span>}
                  </span>
                </div>
                <div className="alm-asset__info">
                  {a.holder_name      && <span className="alm-meta-ico"><User size={13} aria-hidden="true" />{a.holder_name}{a.holder_type !== 'user' ? ` (${t(`alm.holder_${a.holder_type}`)})` : ''}</span>}
                  {a.loan_due         && <span className="alm-meta-ico"><HandCoins size={13} aria-hidden="true" />{t('alm.loan_due_on', { date: fmtDate(a.loan_due) })}</span>}
                  {a.location         && <span className="alm-meta-ico"><MapPin size={13} aria-hidden="true" />{a.location}</span>}
                  {a.serial_number    && <span className="alm-meta-ico"><Hash size={13} aria-hidden="true" />{t('alm.assets_serial_short')} {a.serial_number}</span>}
                  {a.asset_tag        && <span className="alm-meta-ico"><Tag size={13} aria-hidden="true" />{t('alm.assets_tag_short')} {a.asset_tag}</span>}
                  {a.warranty_expiry  && <span className={`alm-meta-ico${a.warranty_expired ? ' alm-tone--danger' : ''}`}>{a.warranty_expired && <AlertTriangle size={13} aria-hidden="true" />}{t('alm.garantia')} {fmtDate(a.warranty_expiry)}</span>}
                  {a.purchase_price   && <span className="alm-meta-ico"><Coins size={13} aria-hidden="true" />{fmtCurrency(a.purchase_price)} · {t('alm.assets_book_short')} {fmtCurrency(a.book_value || 0)}</span>}
                  {a.installed_licenses > 0 && <span className="alm-meta-ico"><Package size={13} aria-hidden="true" />{t('alm.assets_installed_licenses', { n: a.installed_licenses })}</span>}
                  {a.ci_id && <span className="alm-meta-ico"><LinkIcon size={13} aria-hidden="true" />{t('alm.assets_label_ci')}: {a.ci_code} · {a.ci_name}</span>}
                  {a.eol_date && <span>{t('alm.expiry_eol')}: {fmtDate(a.eol_date)}</span>}
                  {a.lease_expiry && <span>{t('alm.expiry_lease')}: {fmtDate(a.lease_expiry)}</span>}
                  {a.next_maintenance_date && <span>{t('alm.expiry_maintenance')}: {fmtDate(a.next_maintenance_date)}</span>}
                </div>
                <div className="alm-actions alm-actions--end">
                  <button type="button" aria-label={t('alm.aria_detail', { name: a.name })} title={t('alm.asset_detail')} onClick={() => setFicha(a.id)} className="alm-icon-btn alm-icon-btn--md"><History size={15} aria-hidden="true" /></button>
                  <button type="button" aria-label={`${t('alm.renewal_open_ticket')} — ${a.name}`} title={t('alm.renewal_open_ticket')} onClick={() => renovar(a)} className="alm-icon-btn alm-icon-btn--md"><RefreshCw size={15} aria-hidden="true" /></button>
                  <button type="button" aria-label={t('alm.aria_edit_asset', { name: a.name })} onClick={() => setModal(a)} className="alm-icon-btn alm-icon-btn--md"><Pencil size={15} aria-hidden="true" /></button>
                  <button type="button" aria-label={t('alm.aria_delete_asset', { name: a.name })} onClick={() => { openConfirmGlobal({ message: t('alm.assets_delete_confirm', { name: a.name }), onConfirm: () => del(a.id), danger: true }) }}
                    className="alm-icon-btn alm-icon-btn--md alm-icon-btn--danger"><Trash2 size={15} aria-hidden="true" /></button>
                </div>
              </div>
            )
          })}
        </div>
      )}
      <div className="alm-pagination">
        <Pagination page={page} totalPages={totalPages} onChange={setPage} total={total} pageSize={ALM_PAGE_SIZE} maxVisible={5} />
      </div>
      {modal !== null && <AssetModal asset={Object.keys(modal).length ? modal : null} vendors={vendors} onClose={() => setModal(null)} />}
      {ficha && <FichaActivo assetId={ficha} onClose={() => setFicha(null)} />}
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
      <div className="u-row-end u-mb-16">
        <Button onClick={() => { setEditing(null); setShowForm(true) }} icon={<Plus size={14} />}>{t('alm.cost_centers_new')}</Button>
      </div>
      {showForm && (
        <div className="alm-card alm-cc-form">
          <h4 className="alm-cc-form__title">{editing ? t('alm.cost_centers_edit') : t('alm.cost_centers_new')}</h4>
          <div className="alm-cc-form__grid">
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="alm-label">{t('alm.cost_centers_label_code')} *</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.code} onChange={s('code')} className="alm-input" placeholder={t('alm.cost_centers_placeholder_code')} /></div>
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="alm-label">{t('alm.cost_centers_label_name')} *</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.name} onChange={s('name')} className="alm-input" placeholder={t('alm.cost_centers_placeholder_name')} /></div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="alm-label">{t('alm.cost_centers_label_budget')}</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" value={form.budget_annual} onChange={s('budget_annual')} className="alm-input" /></div>
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="alm-label">{t('alm.cost_centers_label_currency')}</label><input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.currency} onChange={s('currency')} className="alm-input" /></div>
            <div className="u-col-full"><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="alm-label">{t('alm.cost_centers_label_description')}</label><input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.description} onChange={s('description')} className="alm-input" /></div>
          </div>
          <div className="alm-cc-form__actions">
            <Button variant="secondary" onClick={() => { setShowForm(false); setEditing(null) }}>{t('common.cancel')}</Button>
            <Button onClick={() => save(form)} disabled={isPending || !form.code || !form.name} loading={isPending}>{isPending ? t('common.saving') : editing ? t('common.save') : t('alm.cost_centers_new')}</Button>
          </div>
        </div>
      )}
      {isLoading ? <Spinner /> : centers.length === 0 ? (
        <EmptyState svgIcon={<Briefcase size={36} />} title={t('alm.no_cost_centers')} description={t('alm.cost_centers_empty_desc')} />
      ) : (
        <div className="alm-cc-grid">
          {centers.map(c => (
            <div key={c.id} className="alm-card alm-cc">
              <div className="alm-cc__head">
                <div>
                  <span className="alm-cc__code">{c.code}</span>
                  <div className="alm-cc__name">{c.name}</div>
                </div>
                <div className="u-row-6">
                  <button type="button" aria-label={t('alm.aria_edit_cost_center', { name: c.name })} onClick={() => openEdit(c)} className="alm-icon-btn alm-icon-btn--xs"><Pencil size={13} aria-hidden="true" /></button>
                  <button type="button" aria-label={t('alm.aria_delete_cost_center', { name: c.name })} onClick={() => { openConfirmGlobal({ message: t('alm.cost_centers_delete_confirm', { name: c.name }), onConfirm: () => del(c.id), danger: true }) }}
                    className="alm-icon-btn alm-icon-btn--xs alm-icon-btn--danger"><Trash2 size={13} aria-hidden="true" /></button>
                </div>
              </div>
              {c.budget_annual && <div className="alm-cc__budget">{fmtCurrency(c.budget_annual)}{t('alm.ano')}</div>}
              {c.description && <div className="alm-cc__desc">{c.description}</div>}
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
  const { data: report, isLoading, refetch } = useQuery({
    queryKey: ['alm-compliance'],
    queryFn: () => almExtApi.compliance().then(r => r.data),
  })
  const issues = report?.issues || []

  return (
    <div>
      <div className="alm-compliance-head">
        <div>
          <p className="alm-compliance-intro">
            {t('alm.compliance_intro')}
          </p>
        </div>
        <Button onClick={() => refetch()} variant="secondary" icon={<RefreshCw size={14} />}>{t('common.refresh')}</Button>
      </div>

      {isLoading ? <Spinner /> : (
        <>
          <div className="ds-grid-stats alm-compliance-stats">
            <KpiCard icon={issues.length === 0 ? <CheckCircle2 size={16} /> : <XCircle size={16} />} label={t('alm.compliance_issues')} value={issues.length} warning={issues.length > 0} />
            <KpiCard icon={<ShieldAlert size={16} />} label={t('alm.compliance_critical')} value={report?.critical || 0} danger={(report?.critical || 0) > 0} />
          </div>

          {issues.length === 0 ? (
            <div className="ds-card">
              <EmptyState icon={<CheckCircle2 size={28} />} title={t('alm.compliance_ok')} description={t('alm.compliance_ok_desc')} />
            </div>
          ) : (
            <div className="u-stack-10">
              {issues.map((iss, idx) => (
                <div key={idx} className={`alm-card alm-issue${iss.severity === 'critical' ? ' alm-issue--critical' : ''}`}>
                  <div className="u-row-between">
                    <div>
                      <div className="alm-issue__name">{iss.name}</div>
                      <div className="u-text2-sm">{t(`alm.compliance_issue_${iss.issue}`, iss.params ?? {})}</div>
                    </div>
                    <div className="u-row-center-8">
                      <span className="alm-issue-pill">
                        {t(`alm.compliance_code_${iss.issue}`, iss.issue)}
                      </span>
                      <span className={`alm-issue-pill ${iss.severity === 'critical' ? 'alm-issue-pill--critical' : 'alm-issue-pill--warning'}`}>
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
// Uso real (fase 2): su pestaña vive en pages/alm/uso y se carga al abrirla.
const UsoRealTab = lazy(() => import('./alm/uso/UsoRealTab'))

/** Pestañas por grupo: catálogo, quién tiene qué, dinero y uso real. */
const GRUPOS_DE_PESTANAS: { id: string; tabs: { id: string; icon: ReactNode }[] }[] = [
  { id: 'inventory', tabs: [
    { id: 'dashboard', icon: <LayoutDashboard size={14} /> }, { id: 'licenses', icon: <Key size={14} /> },
    { id: 'assets', icon: <Monitor size={14} /> }, { id: 'vendors', icon: <Building2 size={14} /> },
    { id: 'contracts', icon: <FileText size={14} /> },
  ] },
  { id: 'holders', tabs: [
    { id: 'assignments', icon: <ArrowLeftRight size={14} /> }, { id: 'loans', icon: <HandCoins size={14} /> },
    { id: 'acts', icon: <FileSignature size={14} /> }, { id: 'history', icon: <History size={14} /> },
  ] },
  { id: 'money', tabs: [
    { id: 'costs', icon: <Coins size={14} /> }, { id: 'renewals', icon: <CalendarClock size={14} /> },
    { id: 'reconciliation', icon: <Receipt size={14} /> }, { id: 'cost', icon: <FolderKanban size={14} /> },
    { id: 'compliance', icon: <Scale size={14} /> },
  ] },
  { id: 'usage', tabs: [{ id: 'usage', icon: <Activity size={14} /> }] },
]
const TODAS = GRUPOS_DE_PESTANAS.flatMap(g => g.tabs.map(x => x.id))

export default function ALMPage(): JSX.Element {
  const t = useAppT()
  const [params, setParams] = useSearchParams()
  const pedida = params.get('tab') ?? 'dashboard'
  const tab = TODAS.includes(pedida) ? pedida : 'dashboard'
  const setTab = (id: string) => setParams(p => { const n = new URLSearchParams(p); n.set('tab', id); return n }, { replace: true })
  const grupo = GRUPOS_DE_PESTANAS.find(g => g.tabs.some(x => x.id === tab)) ?? GRUPOS_DE_PESTANAS[0]
  const [fichaDeAsignacion, setFichaDeAsignacion] = useState<{ tipo: 'license' | 'asset'; id: string } | null>(null)

  return (
    <Page
      icon={<Layers size={18} />}
      title={t('nav.alm')}
      subtitle={t('alm.subtitle')}
    >
      <Tabs
        items={GRUPOS_DE_PESTANAS.map(g => ({ id: g.id, label: t(`alm.group_tab_${g.id}`) }))}
        active={grupo.id}
        onChange={id => setTab(GRUPOS_DE_PESTANAS.find(g => g.id === id)?.tabs[0].id ?? 'dashboard')}
        ariaLabel={t('alm.tablist_groups_aria')}
        className="alm-tabs"
      />
      {/* Un grupo de una sola pestaña (Uso real) no lleva segunda barra. */}
      {grupo.tabs.length > 1 && (
        <Tabs
          items={grupo.tabs.map(x => ({ id: x.id, label: t(`alm.tab_${x.id}`), icon: x.icon }))}
          active={tab}
          onChange={setTab}
          ariaLabel={t('alm.tablist_aria')}
          className="alm-tabs"
        />
      )}

      {/* Tabs no pone id a sus botones: el panel se nombra con la etiqueta de la pestaña. */}
      <div id={`alm-panel-${tab}`} role="tabpanel" aria-label={t(`alm.tab_${tab}`)}>
        {tab === 'dashboard'  && <ALMDashboard onNavigate={setTab} />}
        {tab === 'vendors'    && <VendorsTab />}
        {tab === 'contracts'  && <ContractsTab />}
        {tab === 'licenses'   && <LicensesTab />}
        {tab === 'assets'     && <AssetsTab />}
        {tab === 'assignments' && <AsignacionesTab onAbrir={a => setFichaDeAsignacion(a.resource_type === 'license' ? { tipo: 'license', id: a.license_id ?? '' } : { tipo: 'asset', id: a.asset_id ?? '' })} />}
        {tab === 'loans'      && <AsignacionesTab soloPrestamos onAbrir={a => setFichaDeAsignacion({ tipo: 'asset', id: a.asset_id ?? '' })} />}
        {tab === 'acts'       && <ActasTab />}
        {tab === 'history'    && <HistorialPorTitularTab />}
        {tab === 'costs'      && <CostesTab />}
        {tab === 'renewals'   && <RenovacionesTab />}
        {tab === 'reconciliation' && <ConciliacionTab />}
        {tab === 'cost'       && <CostCentersTab />}
        {tab === 'compliance' && <ComplianceTab />}
        {tab === 'usage' && <Suspense fallback={<Spinner />}><UsoRealTab /></Suspense>}
      </div>
      {fichaDeAsignacion?.tipo === 'license' && <FichaLicencia licenseId={fichaDeAsignacion.id} onClose={() => setFichaDeAsignacion(null)} />}
      {fichaDeAsignacion?.tipo === 'asset' && <FichaActivo assetId={fichaDeAsignacion.id} onClose={() => setFichaDeAsignacion(null)} />}
    </Page>
  )
}
