/**
 * Pestaña de activos, su modal, esquema y panel de vencimientos.
 * Troceado de ALMPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useId, useMemo, useState } from 'react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { z } from 'zod'
import { assetsApi, vendorsApi, almExtApi, cmdbApi } from '../../services/api'
import { Buscador,
  Button,
  Spinner,
  EmptyState,
  Modal,
  SelectorDePeriodo,
  Pulsable,
  Select,
  Checkbox,
  useErroresDeCampo,
  Input,
  Textarea, IconButton,
} from '../../components/ui'
import { usePeriodo } from '../../hooks/usePeriodo'
import { SIN_HORA } from '../../utils/periodo'
import Pagination from '../../components/ui/Pagination'
import {
  Monitor,
  Plus,
  Pencil,
  Trash2,
  AlertTriangle,
  RefreshCw,
  User,
  Link as LinkIcon,
  Coins,
  BarChart3,
  MapPin,
  Hash,
  Tag,
  Package,
  History,
  HandCoins,
} from 'lucide-react'
import FichaActivo from '../../components/alm/FichaActivo'
import { fmtCurrency, fmtDate, extractErr } from '../../utils/helpers'
import { useAppT } from '../../i18n/AppLangContext'
import { useFormValidation } from '../../hooks/useFormValidation'
import { useUmbrales } from '../../hooks/useOrgSettings'
import DateInput from '../../components/ui/DateInput'
import { FULL_LIST_SIZE } from '../../constants/pagination'
import {
  ALM_PAGE_SIZE,
  aPagina,
  type Asset,
  ASSET_STATUS_CFG,
  ASSET_TYPES,
  type CambioDeCampo,
  claseCampo,
  type CmdbItem,
  type CostCenter,
  type DatosValidos,
  type PaginaAlm,
  StatusBadge,
  tonoPorDias,
  type Traductor,
  useAjustarPagina,
  useRetardado,
  type Vendor,
} from './compartidoAlm'

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
  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: (d: DatosValidos<typeof esquema>) => isEdit ? assetsApi.update(asset.id, d) : assetsApi.create(d),
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries({ queryKey: ['alm-assets'] }); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('ai.generic_error'))) },
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
          <Input label={<>{t('alm.assets_label_name')} *</>} id={`${idCampo}-1`} value={form.name} onChange={s('name')} aria-invalid={!!validation.errors.name} placeholder={t('alm.assets_placeholder_name')} className="claseCampo validation errors name" />{msg('name')}
          {validation.errors.name && <p className="u-field-error">{validation.errors.name}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="alm-label">{t('alm.assets_label_type')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.type} onChange={s('type')} className="alm-input">
            {Object.keys(ASSET_TYPES).map(k => <option key={k} value={k}>{t(`alm.asset_type_${k}`)}</option>)}
          </Select>{msg('type')}
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="alm-label">{t('alm.assets_label_status')}</label>
          {estadoEditable ? (
            <Select suelto placeholder={false} id={`${idCampo}-3`} value={form.status} onChange={s('status')} className="alm-input">
              {['ordered', 'available'].map(k => <option key={k} value={k}>{t(`alm.asset_status_${k}`)}</option>)}
            </Select>
          ) : (
            <Input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={t(`alm.asset_status_${form.status}`)} readOnly inputClassName="alm-input" />
          )}
          {msg('status')}
          <p className="alm-hint">{t('alm.status_by_actions_hint')}</p>
        </div>
        <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="alm-label">{t('alm.assets_label_brand')}</label><Input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.brand} onChange={s('brand')} placeholder={t('alm.assets_placeholder_brand')} inputClassName="alm-input" />{msg('brand')}</div>
        <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="alm-label">{t('alm.assets_label_model')}</label><Input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.model} onChange={s('model')} inputClassName="alm-input" />{msg('model')}</div>
        <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="alm-label">{t('alm.assets_label_serial')}</label><Input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.serial_number} onChange={s('serial_number')} inputClassName="alm-input" />{msg('serial_number')}</div>
        <div><label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="alm-label">{t('alm.assets_label_tag')}</label><Input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.asset_tag} onChange={s('asset_tag')} placeholder={t('alm.assets_placeholder_tag')} inputClassName="alm-input" />{msg('asset_tag')}</div>
        <div>
          <label htmlFor={`${idCampo}-cc`} className="alm-label">{t('alm.licenses_label_cost_center')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-cc`} value={form.cost_center_id} onChange={s('cost_center_id')} className="alm-input">
            <option value="">{t('alm.licenses_none_cost_center')}</option>
            {costCenters.map(c => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}
          </Select>{msg('cost_center_id')}
        </div>
        <div><label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} className="alm-label">{t('alm.assets_label_location')}</label><Input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} value={form.location} onChange={s('location')} placeholder={t('alm.assets_placeholder_location')} inputClassName="alm-input" />{msg('location')}</div>
        <div>
          <label id={`${idCampo}-et10`} htmlFor={`${idCampo}-10`} className="alm-label">{t('alm.assets_label_vendor')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-10`} value={form.vendor_id} onChange={s('vendor_id')} className="alm-input">
            <option value="">{t('alm.assets_none_vendor')}</option>
            {vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
          </Select>{msg('vendor_id')}
        </div>
        <div>
          <label id={`${idCampo}-et11`} htmlFor={`${idCampo}-11`} className="alm-label">{t('alm.assets_label_condition')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-11`} value={form.condition} onChange={s('condition')} className="alm-input">
            {[['new',t('alm.assets_condition_new')],['good',t('alm.assets_condition_good')],['fair',t('alm.assets_condition_fair')],['poor',t('alm.assets_condition_poor')]].map(([k,l]) => <option key={k} value={k}>{l}</option>)}
          </Select>{msg('condition')}
        </div>
        <div><label id={`${idCampo}-et12`} htmlFor={`${idCampo}-12`} className="alm-label">{t('alm.assets_label_purchase_date')}</label><DateInput id={`${idCampo}-12`} value={form.purchase_date} onChange={s('purchase_date')} className={claseCampo(validation.errors.purchase_date)} aria-invalid={!!validation.errors.purchase_date} />{msg('purchase_date')}</div>
        <div>
          <Input label={t('alm.assets_label_purchase_price')} id={`${idCampo}-13`} type="number" value={form.purchase_price} onChange={s('purchase_price')} aria-invalid={!!validation.errors.purchase_price} />{msg('purchase_price')}
          {validation.errors.purchase_price && <p className="u-field-error">{validation.errors.purchase_price}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et14`} htmlFor={`${idCampo}-14`} className="alm-label">{t('alm.assets_label_warranty_end')}</label>
          <DateInput id={`${idCampo}-14`} value={form.warranty_expiry} onChange={s('warranty_expiry')} className={claseCampo(validation.errors.warranty_expiry)} aria-invalid={!!validation.errors.warranty_expiry} />{msg('warranty_expiry')}
          {validation.errors.warranty_expiry && <p className="u-field-error">{validation.errors.warranty_expiry}</p>}
        </div>
        <div>
          <Input label={t('alm.assets_label_depreciation_years')} id={`${idCampo}-15`} type="number" value={form.depreciation_years} onChange={s('depreciation_years')} aria-invalid={!!validation.errors.depreciation_years} />{msg('depreciation_years')}
          {validation.errors.depreciation_years && <p className="u-field-error">{validation.errors.depreciation_years}</p>}
        </div>
        <div>
          <Input label={t('alm.residual_value')} id={`${idCampo}-res`} type="number" min={0} value={form.residual_value} onChange={s('residual_value')} />{msg('residual_value')}
        </div>
        <div>
          <Input label={t('alm.lease_monthly_cost')} id={`${idCampo}-lease`} type="number" min={0} value={form.lease_monthly_cost} onChange={s('lease_monthly_cost')} />{msg('lease_monthly_cost')}
        </div>
        <div className="alm-check-row">
          <Checkbox id={`${idCampo}-rebill`} checked={form.rebillable} onChange={(_, e) => setForm(f => ({ ...f, rebillable: e.target.checked }))} />
          <label htmlFor={`${idCampo}-rebill`} className="alm-check-label">{t('alm.rebillable_default')}</label>
        </div>
        {showNetwork && <>
          <div><label id={`${idCampo}-et16`} htmlFor={`${idCampo}-16`} className="alm-label">{t('alm.assets_label_ip')}</label><Input id={`${idCampo}-16`} aria-labelledby={`${idCampo}-et16`} value={form.ip_address} onChange={s('ip_address')} placeholder={t('alm.assets_placeholder_ip')} inputClassName="alm-input" />{msg('ip_address')}</div>
          <div><label id={`${idCampo}-et17`} htmlFor={`${idCampo}-17`} className="alm-label">{t('alm.assets_label_hostname')}</label><Input id={`${idCampo}-17`} aria-labelledby={`${idCampo}-et17`} value={form.hostname} onChange={s('hostname')} inputClassName="alm-input" />{msg('hostname')}</div>
          <div><label id={`${idCampo}-et18`} htmlFor={`${idCampo}-18`} className="alm-label">{t('alm.assets_label_os')}</label><Input id={`${idCampo}-18`} aria-labelledby={`${idCampo}-et18`} value={form.os} onChange={s('os')} placeholder={t('alm.assets_placeholder_os')} inputClassName="alm-input" />{msg('os')}</div>
          <div><label id={`${idCampo}-et19`} htmlFor={`${idCampo}-19`} className="alm-label">{t('alm.assets_label_cpu')}</label><Input id={`${idCampo}-19`} aria-labelledby={`${idCampo}-et19`} value={form.cpu} onChange={s('cpu')} placeholder={t('alm.assets_placeholder_cpu')} inputClassName="alm-input" />{msg('cpu')}</div>
          <div>
            <Input label={t('alm.assets_label_ram')} id={`${idCampo}-20`} type="number" value={form.ram_gb} onChange={s('ram_gb')} aria-invalid={!!validation.errors.ram_gb} />{msg('ram_gb')}
            {validation.errors.ram_gb && <p className="u-field-error">{validation.errors.ram_gb}</p>}
          </div>
          <div>
            <Input label={t('alm.assets_label_storage')} id={`${idCampo}-21`} type="number" value={form.storage_gb} onChange={s('storage_gb')} aria-invalid={!!validation.errors.storage_gb} />{msg('storage_gb')}
            {validation.errors.storage_gb && <p className="u-field-error">{validation.errors.storage_gb}</p>}
          </div>
        </>}
        <div className="alm-subhead">
          {t('alm.assets_lifecycle')}
        </div>
        <div className="u-col-full">
          <label className="alm-label" htmlFor="asset-ci">{t('alm.assets_label_ci')}</label>
          <Select suelto placeholder={false} id="asset-ci" value={form.ci_id} onChange={s('ci_id')} className="alm-input">
            <option value="">{t('alm.assets_none_ci')}</option>
            {cis.map(c => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}
          </Select>{msg('ci_id')}
          <p className="alm-hint">{t('alm.assets_ci_hint')}</p>
        </div>
        <div><label className="alm-label" htmlFor="asset-eol">{t('alm.assets_label_eol')}</label><DateInput id="asset-eol" value={form.eol_date} onChange={s('eol_date')} className="alm-input" />{msg('eol_date')}</div>
        <div><label className="alm-label" htmlFor="asset-lease">{t('alm.assets_label_lease')}</label><DateInput id="asset-lease" value={form.lease_expiry} onChange={s('lease_expiry')} className="alm-input" />{msg('lease_expiry')}</div>
        <div><label className="alm-label" htmlFor="asset-maint">{t('alm.assets_label_maintenance')}</label><DateInput id="asset-maint" value={form.next_maintenance_date} onChange={s('next_maintenance_date')} className="alm-input" />{msg('next_maintenance_date')}</div>
        <div><label id="asset-maint-c-et" className="alm-label" htmlFor="asset-maint-c">{t('alm.assets_label_maintenance_contract')}</label><Input id="asset-maint-c" aria-labelledby="asset-maint-c-et" value={form.maintenance_contract} onChange={s('maintenance_contract')} inputClassName="alm-input" />{msg('maintenance_contract')}</div>
        <div className="u-col-full"><label id={`${idCampo}-et22`} htmlFor={`${idCampo}-22`} className="alm-label">{t('alm.assets_label_notes')}</label><Textarea id={`${idCampo}-22`} aria-labelledby={`${idCampo}-et22`} value={form.notes} onChange={s('notes')} rows={3} inputClassName="alm-input" />{msg('notes')}</div>
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
  const umbrales = useUmbrales()
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
              <span className={`alm-expiring__days ${tonoPorDias(f.days_remaining, umbrales, 'muted')}`}>
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

export function AssetsTab() {
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
        <Buscador aria-label={t('alm.assets_search_placeholder')} value={search} onChange={v => { setSearch(v); setPage(1) }} placeholder={t('alm.assets_search_placeholder')} className="alm-toolbar__search" />
        <Select suelto placeholder={false} aria-label={t('alm.assets_filter_type_aria')} value={typeFilter} onChange={e => { setTypeFilter(e.target.value); setPage(1) }} className="alm-input alm-toolbar__select--fixed">
          <option value="">{t('alm.assets_filter_all_types')}</option>
          {Object.keys(ASSET_TYPES).map(k => <option key={k} value={k}>{t(`alm.asset_type_${k}`)}</option>)}
        </Select>
        <Select suelto placeholder={false} aria-label={t('alm.assets_filter_status_aria')} value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1) }} className="alm-input alm-toolbar__select--fixed">
          <option value="">{t('alm.assets_filter_all_statuses')}</option>
          {Object.keys(ASSET_STATUS_CFG).map(k => <option key={k} value={k}>{t(`alm.asset_status_${k}`)}</option>)}
        </Select>
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
                      <Pulsable type="button" className="alm-link-btn u-md-700" onClick={() => setFicha(a.id)}>{a.name}</Pulsable>
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
                <div className="ui-acciones">
                  <IconButton variante="caja" ariaLabel={t('alm.aria_detail', { name: a.name })} title={t('alm.asset_detail')} onClick={() => setFicha(a.id)}><History size={15} aria-hidden="true" /></IconButton>
                  <IconButton variante="caja" ariaLabel={`${t('alm.renewal_open_ticket')} — ${a.name}`} title={t('alm.renewal_open_ticket')} onClick={() => renovar(a)}><RefreshCw size={15} aria-hidden="true" /></IconButton>
                  <IconButton variante="caja" ariaLabel={t('alm.aria_edit_asset', { name: a.name })} onClick={() => setModal(a)}><Pencil size={15} aria-hidden="true" /></IconButton>
                  <IconButton variante="caja" tono="peligro" ariaLabel={t('alm.aria_delete_asset', { name: a.name })} onClick={() => { openConfirmGlobal({ message: t('alm.assets_delete_confirm', { name: a.name }), onConfirm: () => del(a.id), danger: true }) }}><Trash2 size={15} aria-hidden="true" /></IconButton>
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
