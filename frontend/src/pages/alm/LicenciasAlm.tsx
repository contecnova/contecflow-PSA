/**
 * Pestaña de licencias, su modal y esquema de validación.
 * Troceado de ALMPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useId, useMemo, useState, type CSSProperties } from 'react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { z } from 'zod'
import { licensesApi, vendorsApi, almExtApi } from '../../services/api'
import { Buscador, Button, Spinner, EmptyState, Modal, Pulsable, Select, Checkbox, useErroresDeCampo, Input, Textarea, IconButton } from '../../components/ui'
import Pagination from '../../components/ui/Pagination'
import {
  Building2,
  Key,
  Briefcase,
  Plus,
  Pencil,
  Trash2,
  AlertTriangle,
  Coins,
  Globe,
  CalendarClock,
  UserPlus,
  History,
} from 'lucide-react'
import { ICONO_LICENCIA_DEFECTO, METRICAS } from '../../components/alm/almFases'
import AsignarModal from '../../components/alm/AsignarModal'
import FichaLicencia from '../../components/alm/FichaLicencia'
import { fmtCurrency, fmtDate, extractErr } from '../../utils/helpers'
import { useAppT } from '../../i18n/AppLangContext'
import { useFormValidation } from '../../hooks/useFormValidation'
import { useUmbrales } from '../../hooks/useOrgSettings'
import { tonoDe } from '../../utils/umbrales'
import DateInput from '../../components/ui/DateInput'
import {
  ALM_PAGE_SIZE,
  type AlmContract,
  aPagina,
  type CambioDeCampo,
  type CostCenter,
  type DatosValidos,
  ENTORNO_KEY,
  etiquetaDe,
  type License,
  LICENSE_STATUS_CFG,
  LICENSE_TYPES,
  type PaginaAlm,
  StatusBadge,
  type Traductor,
  useAjustarPagina,
  useRetardado,
  type Vendor,
} from './compartidoAlm'

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
  const camposB = useErroresDeCampo()
  const msgB = (k: string) => camposB.de(k) ? <div className="u-field-error">{camposB.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => camposB.limpiar(),
    mutationFn: (d: DatosValidos<typeof esquema>) => isEdit ? licensesApi.update(license.id, d) : licensesApi.create(d),
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries({ queryKey: ['alm-licenses'] }); onClose() },
    onError: (e: unknown) => { if (!camposB.recoger(e)) toast.error(extractErr(e, t('ai.generic_error'))) },
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
          <Input label={<>{t('alm.licenses_label_name')} *</>} id={`${idCampo}-1`} value={form.name} onChange={s('name')} aria-invalid={!!validation.errors.name} placeholder={t('alm.licenses_placeholder_name')} />{msgB('name')}
          {validation.errors.name && <p className="u-field-error">{validation.errors.name}</p>}
        </div>
        <div><Input label={t('alm.licenses_label_product')} id={`${idCampo}-2`} value={form.product_name} onChange={s('product_name')} placeholder={t('alm.licenses_placeholder_product')} />{msgB('product_name')}</div>
        <div><Input label={t('alm.licenses_label_edition')} id={`${idCampo}-3`} value={form.edition} onChange={s('edition')} placeholder={t('alm.licenses_placeholder_edition')} />{msgB('edition')}</div>
        <div><Input label={t('alm.licenses_label_version')} id={`${idCampo}-4`} value={form.version} onChange={s('version')} placeholder={t('alm.licenses_placeholder_version')} />{msgB('version')}</div>
        <div>
          <Select label={t('alm.licenses_label_type')} placeholder={false} id={`${idCampo}-5`} value={form.type} onChange={s('type')}>
            {Object.keys(LICENSE_TYPES).map(k => <option key={k} value={k}>{t(`alm.license_type_${k}`)}</option>)}
          </Select>{msgB('type')}
        </div>
        <div>
          <Select label={t('alm.metric')} placeholder={false} id={`${idCampo}-metric`} value={form.metric} onChange={s('metric')}>
            {METRICAS.map(k => <option key={k} value={k}>{t(`alm.metric_${k}`)}</option>)}
          </Select>{msgB('metric')}
          <p className="alm-hint">{t(`alm.metric_${form.metric}_hint`)}</p>
        </div>
        <div>
          <Input label={t('alm.tier')} id={`${idCampo}-tier`} value={form.tier} onChange={s('tier')} placeholder={t('alm.tier_placeholder')} />{msgB('tier')}
        </div>
        <div>
          <Input label={t('alm.tier_rank')} id={`${idCampo}-tierrank`} type="number" min={0} value={form.tier_rank} onChange={s('tier_rank')} />{msgB('tier_rank')}
          <p className="alm-hint">{t('alm.tier_rank_hint')}</p>
        </div>
        <div>
          <Input label={t('alm.sku')} id={`${idCampo}-sku`} value={form.sku} onChange={s('sku')} />{msgB('sku')}
        </div>
        <div>
          <Select label={t('alm.licenses_label_platform')} placeholder={false} id={`${idCampo}-6`} value={form.platform} onChange={s('platform')}>
            {[['any',t('alm.licenses_platform_all')],['windows','Windows'],['mac','macOS'],['linux','Linux'],['web',t('alm.licenses_platform_web')],['mobile',t('alm.licenses_platform_mobile')]].map(([k,l]) => <option key={k} value={k}>{l}</option>)}
          </Select>{msgB('platform')}
        </div>
        <div>
          <Select label={t('alm.licenses_label_vendor')} placeholder={false} id={`${idCampo}-7`} value={form.vendor_id} onChange={s('vendor_id')}>
            <option value="">{t('alm.licenses_none_vendor')}</option>
            {vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
          </Select>{msgB('vendor_id')}
        </div>
        <div>
          <Select label={t('alm.licenses_label_contract')} placeholder={false} id={`${idCampo}-8`} value={form.contract_id} onChange={s('contract_id')}>
            <option value="">{t('alm.licenses_none_contract')}</option>
            {contracts.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
          </Select>{msgB('contract_id')}
        </div>
        <div>
          <Input label={t('alm.licenses_label_total_seats')} id={`${idCampo}-9`} type="number" value={form.total_seats} onChange={s('total_seats')} aria-invalid={!!validation.errors.total_seats} placeholder={t('alm.licenses_placeholder_seats')} />{msgB('total_seats')}
          {validation.errors.total_seats && <p className="u-field-error">{validation.errors.total_seats}</p>}
        </div>
        <div>
          <Input label={t('alm.contracts_label_annual_cost')} id={`${idCampo}-10`} type="number" value={form.annual_cost} onChange={s('annual_cost')} aria-invalid={!!validation.errors.annual_cost} />{msgB('annual_cost')}
          {validation.errors.annual_cost && <p className="u-field-error">{validation.errors.annual_cost}</p>}
        </div>
        <div>
          <Input label={t('alm.assets_label_purchase_price')} id={`${idCampo}-11`} type="number" value={form.purchase_price} onChange={s('purchase_price')} aria-invalid={!!validation.errors.purchase_price} />{msgB('purchase_price')}
          {validation.errors.purchase_price && <p className="u-field-error">{validation.errors.purchase_price}</p>}
        </div>
        <div>
          <Select label={t('alm.licenses_label_cost_center')} placeholder={false} id={`${idCampo}-12`} value={form.cost_center_id} onChange={s('cost_center_id')}>
            <option value="">{t('alm.licenses_none_cost_center')}</option>
            {costCenters.map(c => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
          </Select>{msgB('cost_center_id')}
        </div>
        <div><DateInput label={t('alm.licenses_label_purchase_date')} id={`${idCampo}-13`} value={form.purchase_date} onChange={s('purchase_date')} aria-invalid={!!validation.errors.purchase_date} />{msgB('purchase_date')}</div>
        <div>
          <DateInput label={t('alm.licenses_label_expiry_date')} id={`${idCampo}-14`} value={form.expiry_date} onChange={s('expiry_date')} aria-invalid={!!validation.errors.expiry_date} />{msgB('expiry_date')}
          {validation.errors.expiry_date && <p className="u-field-error">{validation.errors.expiry_date}</p>}
        </div>
        <div>
          <Select label={t('alm.licenses_label_environment')} placeholder={false} id={`${idCampo}-15`} value={form.environment} onChange={s('environment')}>
            {[['all',t('alm.licenses_env_all')],['prod',t('alm.licenses_env_production')],['staging',t('alm.licenses_env_staging')],['dev',t('alm.licenses_env_dev')]].map(([k,l]) => <option key={k} value={k}>{l}</option>)}
          </Select>{msgB('environment')}
        </div>
        <div>
          <Input label={t('alm.amortization_months')} id={`${idCampo}-amort`} type="number" min={1} value={form.amortization_months} onChange={s('amortization_months')} />{msgB('amortization_months')}
          <p className="alm-hint">{t('alm.amortization_months_hint')}</p>
        </div>
        <div className="alm-check-row">
          <Checkbox id={`${idCampo}-compliance`} checked={form.is_compliance_req} onChange={(_, e) => setForm(f => ({ ...f, is_compliance_req: e.target.checked }))} />
          <label htmlFor={`${idCampo}-compliance`} className="alm-check-label">{t('alm.licenses_requires_compliance')}</label>
        </div>
        <div className="alm-check-row">
          <Checkbox id={`${idCampo}-rebill`} checked={form.rebillable} onChange={(_, e) => setForm(f => ({ ...f, rebillable: e.target.checked }))} />
          <label htmlFor={`${idCampo}-rebill`} className="alm-check-label">{t('alm.rebillable_default')}</label>
        </div>
        <div className="u-col-full">
          <Input label={t('alm.licenses_label_key')} id={`${idCampo}-16`} value={form.license_key} onChange={s('license_key')} autoComplete="off" placeholder={license?.has_key ? t('alm.key_keep', { hint: license.license_key_hint ?? '' }) : t('alm.licenses_placeholder_key')} inputClassName="ds-codigo ds-campo-codigo" />{msgB('license_key')}
          <p className="alm-hint">{t('alm.key_encrypted_hint')}</p>
        </div>
        <div className="u-col-full"><Textarea label={t('alm.contracts_label_notes')} id={`${idCampo}-17`} value={form.notes} onChange={s('notes')} rows={3} />{msgB('notes')}</div>
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

export function LicensesTab() {
  const t = useAppT()
  const umbrales = useUmbrales()
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
        <Buscador aria-label={t('alm.licenses_search_placeholder')} value={search} onChange={v => { setSearch(v); setPage(1) }} placeholder={t('alm.licenses_search_placeholder')} className="alm-toolbar__search" />
        <Select suelto placeholder={false} aria-label={t('alm.licenses_filter_type_aria')} value={typeFilter} onChange={e => { setTypeFilter(e.target.value); setPage(1) }} className="alm-input alm-toolbar__select--fixed">
          <option value="">{t('alm.licenses_filter_all_types')}</option>
          {Object.keys(LICENSE_TYPES).map(k => <option key={k} value={k}>{t(`alm.license_type_${k}`)}</option>)}
        </Select>
        <Select suelto placeholder={false} aria-label={t('alm.licenses_filter_status_aria')} value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1) }} className="alm-input alm-toolbar__select--fixed">
          <option value="">{t('alm.licenses_filter_all_statuses')}</option>
          {Object.keys(LICENSE_STATUS_CFG).map(k => <option key={k} value={k}>{t(`alm.license_status_${k}`)}</option>)}
        </Select>
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
                      <Pulsable type="button" className="alm-link-btn u-md-700" onClick={() => setFicha(lic.id)}>{lic.name}</Pulsable>
                      <StatusBadge status={lic.status} cfg={LICENSE_STATUS_CFG} prefijo="license_status" />
                      {lic.tier && <span className="alm-compliance-tag">{lic.tier}</span>}
                      {lic.pending_count > 0 && <span className="alm-flag">{t('alm.pending_n', { n: lic.pending_count })}</span>}
                      {lic.is_compliance_req && <span className="alm-compliance-tag">{t('alm.compliance_badge')}</span>}
                      {daysLeft !== null && daysLeft >= 0 && tonoDe('vencimiento', daysLeft, umbrales) !== 'success' && (
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
                  <div className="ui-acciones">
                    <Button size="sm" variant="secondary" icon={<UserPlus size={14} aria-hidden="true" />} aria-label={t('alm.aria_assign_license', { name: lic.name })} onClick={() => setAssignModal(lic)}>
                      {t('alm.licenses_assign')}
                    </Button>
                    <IconButton variante="caja" ariaLabel={t('alm.aria_detail', { name: lic.name })} onClick={() => setFicha(lic.id)}><History size={15} aria-hidden="true" /></IconButton>
                    <IconButton variante="caja" ariaLabel={t('alm.aria_edit_license', { name: lic.name })} onClick={() => setModal(lic)}><Pencil size={15} aria-hidden="true" /></IconButton>
                    <IconButton variante="caja" tono="peligro" ariaLabel={t('alm.aria_delete_license', { name: lic.name })} onClick={() => { openConfirmGlobal({ message: t('alm.licenses_delete_confirm', { name: lic.name }), onConfirm: () => del(lic.id), danger: true }) }}><Trash2 size={15} aria-hidden="true" /></IconButton>
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
