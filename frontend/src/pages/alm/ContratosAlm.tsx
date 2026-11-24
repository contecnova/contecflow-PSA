/**
 * Pestaña de contratos, su modal y esquema de validación.
 * Troceado de ALMPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useId, useMemo, useState } from 'react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { z } from 'zod'
import { vendorsApi, almExtApi, type UserListItem } from '../../services/api'
import { Buscador, Button, Spinner, EmptyState, Modal, Pulsable, Select, useErroresDeCampo, Input, Textarea, IconButton } from '../../components/ui'
import { useListaDeUsuarios } from '../../hooks/useListas'
import Pagination from '../../components/ui/Pagination'
import {
  Building2,
  FileText,
  Briefcase,
  Plus,
  Pencil,
  Trash2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  RefreshCw,
  User,
  Coins,
} from 'lucide-react'
import { fmtCurrency, fmtDate, extractErr } from '../../utils/helpers'
import { useAppT } from '../../i18n/AppLangContext'
import { useFormValidation } from '../../hooks/useFormValidation'
import { useOrgSettings } from '../../hooks/useOrgSettings'
import DateInput from '../../components/ui/DateInput'
import {
  ALM_PAGE_SIZE,
  type AlmContract,
  aPagina,
  type CambioDeCampo,
  claseCampo,
  CONTRACT_STATUS,
  CONTRACT_TYPES,
  type CostCenter,
  type DatosValidos,
  etiquetaDe,
  type PaginaAlm,
  StatusBadge,
  type Traductor,
  useAjustarPagina,
  useRetardado,
  type Vendor,
} from './compartidoAlm'

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
  const camposC = useErroresDeCampo()
  const msgC = (k: string) => camposC.de(k) ? <div className="u-field-error">{camposC.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => camposC.limpiar(),
    mutationFn: (d: DatosValidos<typeof esquema>) => isEdit ? almExtApi.updateContract(contract.id, d) : almExtApi.createContract(d),
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries({ queryKey: ['alm-contracts'] }); qc.invalidateQueries({ queryKey: ['alm-dashboard'] }); onClose() },
    onError: (e: unknown) => { if (!camposC.recoger(e)) toast.error(extractErr(e, t('ai.generic_error'))) },
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
          <Input label={<>{t('alm.contracts_label_title')} *</>} id={`${idCampo}-1`} value={form.title} onChange={s('title')} aria-invalid={!!validation.errors.title} placeholder={t('alm.contracts_placeholder_title')} className="claseCampo validation errors title" />{msgC('title')}
          {validation.errors.title && <p className="u-field-error">{validation.errors.title}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="alm-label">{t('alm.contracts_label_vendor')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.vendor_id} onChange={s('vendor_id')} className="alm-input">
            <option value="">{t('alm.contracts_none_vendor')}</option>
            {vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
          </Select>{msgC('vendor_id')}
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="alm-label">{t('alm.contracts_label_type')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-3`} value={form.type} onChange={s('type')} className="alm-input">
            {Object.keys(CONTRACT_TYPES).map(k => <option key={k} value={k}>{t(`alm.contract_type_${k}`)}</option>)}
          </Select>{msgC('type')}
        </div>
        <div>
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="alm-label">{t('alm.contracts_label_status')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-4`} value={form.status} onChange={s('status')} className="alm-input">
            {Object.keys(CONTRACT_STATUS).map(k => <option key={k} value={k}>{t(`alm.contract_status_${k}`)}</option>)}
          </Select>{msgC('status')}
        </div>
        <div>
          <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="alm-label">{t('alm.contracts_label_billing_cycle')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-5`} value={form.billing_cycle} onChange={s('billing_cycle')} className="alm-input">
            {[['one_time',t('alm.contracts_cycle_one_time')],['monthly',t('alm.contracts_cycle_monthly')],['quarterly',t('alm.contracts_cycle_quarterly')],['annual',t('alm.contracts_cycle_annual')],['biennial',t('alm.contracts_cycle_biennial')]].map(([k,l]) => <option key={k} value={k}>{l}</option>)}
          </Select>{msgC('billing_cycle')}
        </div>
        <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="alm-label">{t('alm.contracts_label_start_date')}</label><DateInput id={`${idCampo}-6`} value={form.start_date} onChange={s('start_date')} className={claseCampo(validation.errors.start_date)} aria-invalid={!!validation.errors.start_date} />{msgC('start_date')}</div>
        <div>
          <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="alm-label">{t('alm.contracts_label_end_date')}</label>
          <DateInput id={`${idCampo}-7`} value={form.end_date} onChange={s('end_date')} className={claseCampo(validation.errors.end_date)} aria-invalid={!!validation.errors.end_date} />{msgC('end_date')}
          {validation.errors.end_date && <p className="u-field-error">{validation.errors.end_date}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} className="alm-label">{t('alm.contracts_label_renewal_date')}</label>
          <DateInput id={`${idCampo}-8`} value={form.renewal_date} onChange={s('renewal_date')} className={claseCampo(validation.errors.renewal_date)} aria-invalid={!!validation.errors.renewal_date} />{msgC('renewal_date')}
          {validation.errors.renewal_date && <p className="u-field-error">{validation.errors.renewal_date}</p>}
        </div>
        <div>
          <span id={`${idCampo}-auto-et`} className="alm-label">{t('alm.contracts_label_auto_renew')}</span>
          <div className="alm-toggle-row" role="group" aria-labelledby={`${idCampo}-auto-et`}>
            {[true, false].map(v => (
              <Pulsable key={String(v)} type="button" aria-pressed={form.auto_renew === v} onClick={() => setForm(f => ({ ...f, auto_renew: v }))}
                className="alm-toggle">
                {v ? <><CheckCircle2 size={14} aria-hidden="true" /> {t('alm.contracts_yes')}</> : <><XCircle size={14} aria-hidden="true" /> {t('alm.contracts_no')}</>}
              </Pulsable>
            ))}
          </div>
        </div>
        <div>
          <Input label={t('alm.contracts_label_notice_days')} id={`${idCampo}-9`} type="number" value={form.notice_days} onChange={s('notice_days')} aria-invalid={!!validation.errors.notice_days} />{msgC('notice_days')}
          {validation.errors.notice_days && <p className="u-field-error">{validation.errors.notice_days}</p>}
        </div>
        <div>
          <Input label={t('alm.contracts_label_uc_hours')} id="contract-uc" type="number" min={0} step="0.5" value={form.resolution_hours} onChange={s('resolution_hours')} aria-invalid={!!validation.errors.resolution_hours} />{msgC('resolution_hours')}
          {validation.errors.resolution_hours
            ? <p className="u-field-error">{validation.errors.resolution_hours}</p>
            : <p className="alm-hint">{t('alm.contracts_uc_hint')}</p>}
        </div>
        <div>
          <Input label={t('alm.contracts_label_uc_response')} id="contract-uc-resp" type="number" min={0} step="0.5" value={form.response_hours} onChange={s('response_hours')} aria-invalid={!!validation.errors.response_hours} />{msgC('response_hours')}
          {validation.errors.response_hours && <p className="u-field-error">{validation.errors.response_hours}</p>}
        </div>
        <div>
          <Input label={t('alm.contracts_label_total_value')} id={`${idCampo}-10`} type="number" value={form.total_value} onChange={s('total_value')} aria-invalid={!!validation.errors.total_value} />{msgC('total_value')}
          {validation.errors.total_value && <p className="u-field-error">{validation.errors.total_value}</p>}
        </div>
        <div>
          <Input label={t('alm.contracts_label_annual_cost')} id={`${idCampo}-11`} type="number" value={form.annual_value} onChange={s('annual_value')} aria-invalid={!!validation.errors.annual_value} />{msgC('annual_value')}
          {validation.errors.annual_value && <p className="u-field-error">{validation.errors.annual_value}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et12`} htmlFor={`${idCampo}-12`} className="alm-label">{t('alm.contracts_label_owner')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-12`} value={form.owner_id} onChange={s('owner_id')} className="alm-input">
            <option value="">{t('alm.contracts_none_owner')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </Select>{msgC('owner_id')}
        </div>
        <div>
          <label id={`${idCampo}-et13`} htmlFor={`${idCampo}-13`} className="alm-label">{t('alm.contracts_label_cost_center')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-13`} value={form.cost_center_id} onChange={s('cost_center_id')} className="alm-input">
            <option value="">{t('alm.contracts_none_cost_center')}</option>
            {costCenters.map(c => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
          </Select>{msgC('cost_center_id')}
        </div>
        <div><label id={`${idCampo}-et14`} htmlFor={`${idCampo}-14`} className="alm-label">{t('alm.contracts_label_po')}</label><Input id={`${idCampo}-14`} aria-labelledby={`${idCampo}-et14`} value={form.po_number} onChange={s('po_number')} inputClassName="alm-input" />{msgC('po_number')}</div>
        <div><label id={`${idCampo}-et15`} htmlFor={`${idCampo}-15`} className="alm-label">{t('alm.contracts_label_payment_method')}</label><Input id={`${idCampo}-15`} aria-labelledby={`${idCampo}-et15`} value={form.payment_method} onChange={s('payment_method')} placeholder={t('alm.contracts_placeholder_payment_method')} inputClassName="alm-input" />{msgC('payment_method')}</div>
        <div className="u-col-full"><label id={`${idCampo}-et16`} htmlFor={`${idCampo}-16`} className="alm-label">{t('alm.contracts_label_document_url')}</label><Input id={`${idCampo}-16`} aria-labelledby={`${idCampo}-et16`} value={form.document_url} onChange={s('document_url')} placeholder={t('alm.contracts_placeholder_document_url')} inputClassName="alm-input" />{msgC('document_url')}</div>
        <div className="u-col-full"><label id={`${idCampo}-et17`} htmlFor={`${idCampo}-17`} className="alm-label">{t('alm.contracts_label_notes')}</label><Textarea id={`${idCampo}-17`} aria-labelledby={`${idCampo}-et17`} value={form.notes} onChange={s('notes')} rows={3} inputClassName="alm-input" />{msgC('notes')}</div>
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

export function ContractsTab() {
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
  const { data: users = [] } = useListaDeUsuarios()
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
        <Buscador aria-label={t('alm.contracts_search_placeholder')} value={search} onChange={v => { setSearch(v); setPage(1) }} placeholder={t('alm.contracts_search_placeholder')} className="alm-toolbar__search alm-toolbar__search--wide" />
        <Select suelto placeholder={false} aria-label={t('alm.contracts_filter_status_aria')} value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1) }} className="alm-input alm-toolbar__select--fixed">
          <option value="">{t('alm.contracts_filter_all_statuses')}</option>
          {Object.keys(CONTRACT_STATUS).map(k => <option key={k} value={k}>{t(`alm.contract_status_${k}`)}</option>)}
        </Select>
        <Pulsable type="button" aria-pressed={urgentOnly} aria-label={t('alm.contracts_urgent_only_aria')} onClick={() => { setUrgentOnly(u => !u); setPage(1) }}
          className="alm-urgent">
          <AlertTriangle size={14} aria-hidden="true" /> {t('alm.contracts_urgent_only')}
        </Pulsable>
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
                <div className="ui-acciones">
                  <IconButton variante="caja" ariaLabel={t('alm.aria_edit_contract', { name: c.title })} onClick={() => setModal(c)}><Pencil size={15} aria-hidden="true" /></IconButton>
                  <IconButton variante="caja" tono="peligro" ariaLabel={t('alm.aria_delete_contract', { name: c.title })} onClick={() => { openConfirmGlobal({ message: t('alm.contracts_delete_confirm_named', { name: c.title }), onConfirm: () => del(c.id), danger: true }) }}><Trash2 size={15} aria-hidden="true" /></IconButton>
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
