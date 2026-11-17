import { useState, useId, useMemo } from 'react'
import type { CSSProperties, ChangeEvent } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { projectsApi, contractsApi } from '../services/api'
import type { ContratoDeServicio } from '../services/api/tipos-finanzas'
import DocumentosDeFicha from '../components/conectores/DocumentosDeFicha'
import { Button, Modal, Spinner, EmptyState, ClientSelect, KpiCard, useSort, SortableTH, Pulsable, Select, useErroresDeCampo } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Building2, CalendarClock, ClipboardList, Coins, LayoutGrid, List, Pencil, Plus, ScrollText, Wrench } from 'lucide-react'
import { fmtDate, fmtNumber, extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAppT } from '../i18n/AppLangContext'
import { useFormValidation } from '../hooks/useFormValidation'
import DateInput from '../components/ui/DateInput'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import './ContractsPage.css'

type Traductor = ReturnType<typeof useAppT>

// ── Contract / WorkOrder shapes (contract_service.serialize_contract) ─────────
type Contract = ContratoDeServicio
type ApiErr = { response?: { data?: { detail?: string } } }

// Etiquetas en i18n (`contractspage.tipo_<v>`, `estado_<v>`, `ot_<v>`); colores = tokens del tema.
const CONTRACT_TYPES = ['fixed_price', 'time_material', 'retainer', 'hourly_bag'] as const
const STATUS_COLOR: Record<string, string> = {
  draft: 'var(--text-2)',
  active: 'var(--accent)',
  expired: 'var(--danger)',
  cancelled: 'var(--text-3)',
}
const WO_COLOR: Record<string, string> = {
  open: 'var(--accent)',
  in_progress: 'var(--warning)',
  completed: 'var(--success)',
  invoiced: 'var(--purple)',
}

/** Color de datos → custom property que consumen las clases `.ctr-*`. */
const colorVar = (color: string): CSSProperties => ({ '--ctr-color': color } as CSSProperties)
/** ClientSelect (components/ui) solo acepta `style`: igualamos su relleno al de `.ctr-input`. */
const numeroOpcional = (msg: string) =>
  z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, msg).optional())

function crearEsquemaContrato(t: Traductor) {
  return z.object({
    name: z.string().trim().min(1, t('contractspage.err_nombre')),
    project_id: z.string().trim().min(1, t('contractspage.err_proyecto')),
    client_id: z.union([z.string(), z.number()]).refine((v) => `${v}`.trim().length > 0, t('contractspage.err_cliente')),
    client_name: z.string().optional(),
    client_contact: z.string().optional(),
    contract_type: z.enum(CONTRACT_TYPES),
    status: z.enum(['draft', 'active', 'expired', 'cancelled']),
    total_amount: numeroOpcional(t('contractspage.err_importe_negativo')),
    hourly_rate: numeroOpcional(t('contractspage.err_tarifa_negativa')),
    hours_bag: numeroOpcional(t('contractspage.err_horas_negativas')),
    monthly_retainer: numeroOpcional(t('contractspage.err_retainer_negativo')),
    start_date: z.string().optional(),
    end_date: z.string().optional(),
    signed_date: z.string().optional(),
    payment_terms: z.string().optional(),
    notes: z.string().optional(),
  }).superRefine((values, ctx) => {
    if (values.start_date && values.end_date && values.end_date < values.start_date) {
      ctx.addIssue({ code: 'custom', path: ['end_date'], message: t('contractspage.err_fin_antes_inicio') })
    }
    if (values.contract_type === 'fixed_price' && typeof values.total_amount !== 'number') {
      ctx.addIssue({ code: 'custom', path: ['total_amount'], message: t('contractspage.err_importe_obligatorio') })
    }
    if (values.contract_type === 'time_material' && typeof values.hourly_rate !== 'number') {
      ctx.addIssue({ code: 'custom', path: ['hourly_rate'], message: t('contractspage.err_tarifa_tm') })
    }
    if (values.contract_type === 'hourly_bag') {
      if (typeof values.hours_bag !== 'number') {
        ctx.addIssue({ code: 'custom', path: ['hours_bag'], message: t('contractspage.err_bolsa_obligatoria') })
      }
      if (typeof values.hourly_rate !== 'number') {
        ctx.addIssue({ code: 'custom', path: ['hourly_rate'], message: t('contractspage.err_tarifa_bolsa') })
      }
    }
    if (values.contract_type === 'retainer' && typeof values.monthly_retainer !== 'number') {
      ctx.addIssue({ code: 'custom', path: ['monthly_retainer'], message: t('contractspage.err_retainer_obligatorio') })
    }
  })
}

function crearEsquemaOT(t: Traductor) {
  return z.object({
    name: z.string().trim().min(1, t('contractspage.err_nombre_ot')),
    amount: numeroOpcional(t('contractspage.err_importe_negativo')),
    hours: numeroOpcional(t('contractspage.err_horas_negativas')),
    start_date: z.string().optional(),
    end_date: z.string().optional(),
  }).superRefine((values, ctx) => {
    if (values.start_date && values.end_date && values.end_date < values.start_date) {
      ctx.addIssue({ code: 'custom', path: ['end_date'], message: t('contractspage.err_fin_antes_inicio_ot') })
    }
  })
}

/** Props de un campo con error: aria-invalid (lo pinta `.ctr-input`) + enlace al mensaje. */
function propsDeError(errors: Record<string, string | undefined>, key: string, idBase: string) {
  return errors[key] ? { 'aria-invalid': true as const, 'aria-describedby': `${idBase}-err-${key}` } : {}
}
function MensajeError({ errors, campo, idBase }: { errors: Record<string, string | undefined>; campo: string; idBase: string }) {
  return errors[campo] ? <p id={`${idBase}-err-${campo}`} className="u-field-error">{errors[campo]}</p> : null
}

function ContractFormModal({ contract, onClose }: { contract?: Contract | null; onClose: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!contract?.id
  const { data: projects = [] } = useQuery<Array<{ id: string; code?: string; name?: string }>>({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => ((r.data as { items?: unknown[] })?.items ?? (r.data as unknown[]) ?? []) as Array<{ id: string; code?: string; name?: string }>) })
  const [form, setForm] = useState({
    name: contract?.name || '',
    project_id: contract?.project_id || '',
    client_id: contract?.client_id || '',
    client_name: contract?.client_name || '',
    client_contact: contract?.client_contact || '',
    contract_type: contract?.contract_type || 'time_material',
    status: contract?.status || 'draft',
    total_amount: contract?.total_amount || '',
    hourly_rate: contract?.hourly_rate || '',
    hours_bag: contract?.hours_bag || '',
    monthly_retainer: contract?.monthly_retainer || '',
    start_date: contract?.start_date || '',
    end_date: contract?.end_date || '',
    signed_date: contract?.signed_date || '',
    payment_terms: contract?.payment_terms || '',
    notes: contract?.notes || '',
  })
  const contractSchema = useMemo(() => crearEsquemaContrato(t), [t])
  const validation = useFormValidation(contractSchema)
  const campos = useErroresDeCampo()
  const errs = { ...campos.errores, ...(validation.errors as Record<string, string | undefined>) }
  const err = (k: string) => propsDeError(errs, k, idCampo)
  const msg = (k: string) => <MensajeError errors={errs} campo={k} idBase={idCampo} />
  const set = (k: string) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
    campos.limpiar(k)
  }

  const { mutate, isPending } = useMutation({
    mutationFn: (data: Record<string, unknown>) => isEdit ? contractsApi.update(contract!.id, data) : contractsApi.create(data),
    onMutate: () => campos.limpiar(),
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries({ queryKey: ['contracts'] }); qc.invalidateQueries({ queryKey: ['client-detail'] }); qc.invalidateQueries({ queryKey: ['clients'] }); onClose() },
    onError: (e: ApiErr) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate(result.data as Record<string, unknown>)
  }

  const tarifaHora = (
    <div>
      <label htmlFor={`${idCampo}-tarifa`} className="ctr-label">{t('contractspage.tarifa_hora', { simbolo: fmtMoneda.simbolo })}</label>
      <input id={`${idCampo}-tarifa`} type="number" value={form.hourly_rate} onChange={set('hourly_rate')} className="ctr-input" placeholder={t('contracts.tarifa_por_hora')} {...err('hourly_rate')} />
      {msg('hourly_rate')}
    </div>
  )

  return (
    <Modal open title={isEdit ? t('contractspage.editar_contrato') : t('contractspage.nuevo_contrato')} onClose={onClose} width={620}>
      <div className="u-grid2-14">
        <div className="u-col-full">
          <label id={`${idCampo}-eta186`} htmlFor={`${idCampo}-a186`} className="ctr-label">{t('contractspage.campo_nombre')}</label>
          <input id={`${idCampo}-a186`} aria-labelledby={`${idCampo}-eta186`} value={form.name} onChange={set('name')} className="ctr-input" placeholder={t('contracts.nombre_del_contrato')} {...err('name')} />
          {msg('name')}
        </div>
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="ctr-label">{t('contractspage.campo_proyecto')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-1`} value={form.project_id} onChange={set('project_id')} className="ctr-input" {...err('project_id')}>
            <option value="">{t('contractspage.seleccionar')}</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </Select>
          {msg('project_id')}
        </div>
        <div>
          <label id={`${idCampo}-eta199`} htmlFor={`${idCampo}-a199`} className="ctr-label">{t('contractspage.campo_cliente')}</label>
          {/* ClientSelect no acepta className: el estado de error usa el mismo estilo del validador. */}
          <ClientSelect id={`${idCampo}-a199`} aria-labelledby={`${idCampo}-eta199`}
            value={String(form.client_id)}
            onChange={(id, client) => {
              setForm(f => ({ ...f, client_id: id, client_name: client ? client.name : '' }))
              validation.clearFieldError('client_id')
              campos.limpiar('client_id')
            }}
            placeholder={t('contractspage.seleccionar_cliente')}
            className={validation.inputClass('contracts-page-cliente', 'client_id')}
          />
          {msg('client_id')}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="ctr-label">{t('contracts.tipo_de_contrato')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.contract_type} onChange={set('contract_type')} className="ctr-input" {...err('contract_type')}>
            {CONTRACT_TYPES.map(v => <option key={v} value={v}>{t(`contractspage.tipo_${v}`)}</option>)}
          </Select>
          {msg('contract_type')}
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="ctr-label">{t('contractspage.campo_estado')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-3`} value={form.status} onChange={set('status')} className="ctr-input">
            {Object.keys(STATUS_COLOR).map(v => <option key={v} value={v}>{t(`contractspage.estado_${v}`)}</option>)}
          </Select>
          {msg('status')}
        </div>
        {form.contract_type === 'fixed_price' && (
          <div>
            <label htmlFor={`${idCampo}-importe`} className="ctr-label">{t('contractspage.importe_total', { simbolo: fmtMoneda.simbolo })}</label>
            <input id={`${idCampo}-importe`} type="number" value={form.total_amount} onChange={set('total_amount')} className="ctr-input" placeholder={t('contractspage.ph_importe_total')} {...err('total_amount')} />
            {msg('total_amount')}
          </div>
        )}
        {form.contract_type === 'time_material' && tarifaHora}
        {form.contract_type === 'hourly_bag' && (
          <>
            <div>
              <label htmlFor={`${idCampo}-bolsa`} className="ctr-label">{t('contracts.bolsa_de_horas')}</label>
              <input id={`${idCampo}-bolsa`} type="number" value={form.hours_bag} onChange={set('hours_bag')} className="ctr-input" placeholder={t('contractspage.ph_horas_incluidas')} {...err('hours_bag')} />
              {msg('hours_bag')}
            </div>
            {tarifaHora}
          </>
        )}
        {form.contract_type === 'retainer' && (
          <div>
            <label htmlFor={`${idCampo}-retainer`} className="ctr-label">{t('contractspage.retainer_mensual', { simbolo: fmtMoneda.simbolo })}</label>
            <input id={`${idCampo}-retainer`} type="number" value={form.monthly_retainer} onChange={set('monthly_retainer')} className="ctr-input" placeholder={t('contractspage.ph_importe_mensual')} {...err('monthly_retainer')} />
            {msg('monthly_retainer')}
          </div>
        )}
        <div>
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="ctr-label">{t('contractspage.fecha_inicio')}</label>
          <DateInput id={`${idCampo}-4`} value={form.start_date} onChange={set('start_date')} className="ctr-input" {...err('start_date')} />
          {msg('start_date')}
        </div>
        <div>
          <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="ctr-label">{t('contractspage.fecha_fin')}</label>
          <DateInput id={`${idCampo}-5`} value={form.end_date} onChange={set('end_date')} className="ctr-input" {...err('end_date')} />
          {msg('end_date')}
        </div>
        <div>
          <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="ctr-label">{t('contractspage.fecha_firma')}</label>
          <DateInput id={`${idCampo}-6`} value={form.signed_date} onChange={set('signed_date')} className="ctr-input" />
          {msg('signed_date')}
        </div>
        <div>
          <label htmlFor={`${idCampo}-pago`} className="ctr-label">{t('contracts.condiciones_de_pago')}</label>
          <input id={`${idCampo}-pago`} value={form.payment_terms} onChange={set('payment_terms')} className="ctr-input" aria-label={t('contracts.condiciones_de_pago')} placeholder={t('contractspage.ph_condiciones_pago')} />
          {msg('payment_terms')}
        </div>
        <div className="u-col-full">
          <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="ctr-label">{t('contractspage.notas')}</label>
          <textarea id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.notes} onChange={set('notes')} rows={2} className="ctr-input" />
          {msg('notes')}
        </div>
        <div className="ctr-form-actions">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={submit} disabled={isPending} loading={isPending}>
            {isPending ? t('common.saving') : isEdit ? t('common.save') : t('contractspage.crear_contrato')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function ContractDetail({ contract, onClose, onEdit }: { contract: Contract; onClose: () => void; onEdit: (c: Contract) => void }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showWO, setShowWO] = useState(false)
  const [woForm, setWoForm] = useState<Record<string, string>>({ name: '', amount: '', hours: '', start_date: '', end_date: '' })
  const workOrderSchema = useMemo(() => crearEsquemaOT(t), [t])
  const woValidation = useFormValidation(workOrderSchema)
  const errs = woValidation.errors as Record<string, string | undefined>
  const err = (k: string) => propsDeError(errs, k, idCampo)
  const msg = (k: string) => <MensajeError errors={errs} campo={k} idBase={idCampo} />
  const setWo = (k: string) => (e: ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setWoForm(f => ({ ...f, [k]: value }))
    woValidation.clearFieldError(k)
  }
  const dinero = (n: number | null | undefined) => fmtMoneda(n, { decimales: 0 })

  const { mutate: createWO } = useMutation({
    mutationFn: (data: Record<string, unknown>) => contractsApi.createWorkOrder(contract.id, data),
    onSuccess: () => { woValidation.setErrors({}); qc.invalidateQueries({ queryKey: ['contracts'] }); setShowWO(false); setWoForm({ name: '', amount: '', hours: '', start_date: '', end_date: '' }) },
    onError: (e: ApiErr) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: updateWOStatus } = useMutation({
    mutationFn: ({ woId, status }: { woId: string; status: string }) => contractsApi.updateWorkOrderStatus(contract.id, woId, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contracts'] }),
    onError: (e: ApiErr) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const estado = STATUS_COLOR[contract.status || ''] ? contract.status! : 'draft'

  const submitWO = () => {
    const result = woValidation.validateForm(woForm)
    if (!result.success) return
    createWO(result.data as Record<string, unknown>)
  }

  const facts = [
    { label: t('contractspage.dato_cliente'), value: contract.client_name || '—' },
    { label: t('contractspage.dato_importe'), value: contract.total_amount ? dinero(contract.total_amount) : contract.monthly_retainer ? t('contractspage.por_mes', { importe: dinero(contract.monthly_retainer) }) : '—' },
    { label: t('contractspage.dato_tarifa'), value: contract.hourly_rate ? t('contractspage.por_hora', { importe: fmtMoneda(contract.hourly_rate) }) : '—' },
    { label: t('contractspage.dato_inicio'), value: contract.start_date ? fmtDate(contract.start_date) : '—' },
    { label: t('contractspage.dato_fin'), value: contract.end_date ? fmtDate(contract.end_date) : '—' },
    { label: t('contractspage.dato_firma'), value: contract.signed_date ? fmtDate(contract.signed_date) : '—' },
    ...(contract.hours_bag ? [{ label: t('contractspage.dato_bolsa'), value: t('contractspage.bolsa_uso', { usadas: fmtNumber(contract.hours_used || 0, 0), total: fmtNumber(contract.hours_bag, 0), pct: contract.hours_pct || 0 }) }] : []),
    ...(contract.payment_terms ? [{ label: t('contractspage.dato_pago'), value: contract.payment_terms }] : []),
  ]

  return (
    <Modal open title={`${contract.code} — ${contract.name}`} onClose={onClose} width={760}>
      <div className="ctr-detail-head">
        <span className="ctr-status-pill" style={colorVar(STATUS_COLOR[estado])}>{t(`contractspage.estado_${estado}`)}</span>
        <span className="u-text2-sm">{contract.contract_type_label}</span>
      </div>
      <dl className="ctr-facts">
        {facts.map(({ label, value }) => (
          <div key={label} className="ctr-fact">
            <dt className="ctr-fact__label">{label}</dt>
            <dd className="u-base-600">{value}</dd>
          </div>
        ))}
      </dl>

      {/* Work Orders */}
      <div className="u-mb-16">
        <div className="ctr-section-head">
          <h4 className="ctr-section-title">{t('contractspage.ordenes_n', { count: contract.work_orders?.length || 0 })}</h4>
          <Button size="sm" onClick={() => setShowWO(true)} icon={<Plus size={14} />}>{t('contracts.nueva_ot')}</Button>
        </div>
        {contract.work_orders?.length === 0 ? (
          <EmptyState icon={<Wrench size={28} />} title={t('contracts.sin_ordenes_de_trabajo')} />
        ) : (
          <div className="u-stack-8">
            {contract.work_orders!.map(wo => {
              const woEstado = WO_COLOR[wo.status || ''] ? wo.status! : 'open'
              return (
                <div key={wo.id} className="ctr-wo">
                  <div className="u-flex1">
                    <div className="u-base-600">{wo.code} — {wo.name}</div>
                    <div className="u-text2-xs">
                      {wo.amount ? dinero(wo.amount) : ''} {wo.hours ? `· ${fmtNumber(wo.hours, 0)}h` : ''}
                      {wo.start_date ? ` · ${fmtDate(wo.start_date)}` : ''}
                    </div>
                  </div>
                  <Select suelto placeholder={false} value={wo.status} onChange={e => updateWOStatus({ woId: wo.id, status: e.target.value })}
                    aria-label={t('contractspage.estado_de_ot', { code: wo.code })}
                    className="ctr-wo-status" style={colorVar(WO_COLOR[woEstado])}>
                    {Object.keys(WO_COLOR).map(v => <option key={v} value={v}>{t(`contractspage.ot_${v}`)}</option>)}
                  </Select>
                </div>
              )
            })}
          </div>
        )}

        {showWO && (
          <div className="ctr-wo-form">
            <div className="ctr-wo-form__grid">
              <div>
                <input value={woForm.name} onChange={setWo('name')} className="ctr-input" placeholder={t('contracts.nombre_de_la_orden')} aria-label={t('contracts.nombre_de_la_orden')} {...err('name')} />
                {msg('name')}
              </div>
              <div>
                <input type="number" value={woForm.amount} onChange={setWo('amount')} className="ctr-input" placeholder={t('contractspage.dato_importe')} aria-label={t('contractspage.dato_importe')} {...err('amount')} />
                {msg('amount')}
              </div>
              <div>
                <input type="number" value={woForm.hours} onChange={setWo('hours')} className="ctr-input" placeholder={t('contractspage.horas')} aria-label={t('contractspage.horas')} {...err('hours')} />
                {msg('hours')}
              </div>
              <div><DateInput value={woForm.start_date} onChange={setWo('start_date')} className="ctr-input" aria-label={t('contractspage.fecha_inicio')} {...err('start_date')} /></div>
              <div>
                <DateInput value={woForm.end_date} onChange={setWo('end_date')} className="ctr-input" aria-label={t('contractspage.fecha_fin')} {...err('end_date')} />
                {msg('end_date')}
              </div>
            </div>
            <div className="u-row-8">
              <Button size="sm" onClick={submitWO}>{t('contractspage.crear_ot')}</Button>
              <Button size="sm" variant="secondary" onClick={() => setShowWO(false)}>{t('common.cancel')}</Button>
            </div>
          </div>
        )}
      </div>

      {/* Revisión 2026-11: el contrato firmado y sus anexos viven en contecmind, con versiones y aprobación. */}
      <div className="u-mb-20"><DocumentosDeFicha ficha="contract" id={contract.id} preguntar /></div>

      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>{t('common.close')}</Button>
        <Button icon={<Pencil size={14} />} onClick={() => { onClose(); onEdit(contract) }}>{t('common.edit')}</Button>
      </div>
    </Modal>
  )
}

export default function ContractsPage(): JSX.Element {
  const t = useAppT()
  const fmtMoneda = useFormatoMoneda()
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<Contract | null>(null)
  const [detail, setDetail] = useState<Contract | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [view, setView] = useState('list')

  const { data: contracts = [], isLoading } = useQuery<Contract[]>({
    queryKey: ['contracts', statusFilter],
    queryFn: () => contractsApi.list(statusFilter ? { status: statusFilter } : {}).then(r => r.data),
  })

  const dinero = (n: number | null | undefined) => fmtMoneda(n, { decimales: 0 })
  const importeCorto = (c: Contract) => c.total_amount ? dinero(c.total_amount)
    : c.monthly_retainer ? t('contractspage.por_mes_corto', { importe: dinero(c.monthly_retainer) })
    : c.hours_bag ? `${fmtNumber(c.hours_bag, 0)}h` : '—'
  const estadoDe = (c: Contract) => (STATUS_COLOR[c.status || ''] ? c.status! : 'draft')

  // Contratos que vencen en los próximos 90 días
  const today = new Date()
  const expiring = contracts.filter(c => {
    if (!c.end_date || c.status === 'cancelled' || c.status === 'expired') return false
    const end = new Date(c.end_date)
    const daysLeft = Math.ceil((end.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
    return daysLeft >= 0 && daysLeft <= 90
  }).map(c => {
    const daysLeft = Math.ceil((new Date(c.end_date!).getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
    return { ...c, daysLeft }
  }).sort((a, b) => a.daysLeft - b.daysLeft)

  const totalValue = contracts.reduce((s, c) => {
    const totalAmount = Number(c.total_amount) || 0
    const retainer = Number(c.monthly_retainer) || 0
    return s + (totalAmount > 0 ? totalAmount : retainer * 12)
  }, 0)
  const active = contracts.filter(c => c.status === 'active').length
  const { sort: contractSort, setSort: setContractSort, sortedData: sortedContracts } = useSort<Contract>(contracts, 'name')

  const otsAbiertas = contracts.reduce((s, c) => s + (c.work_orders?.filter(w => w.status === 'open').length || 0), 0)
  const newContractButton = (
    <Button onClick={() => setShowCreate(true)} icon={<Plus size={14} />}>{t('contracts.new_contract')}</Button>
  )

  return (
    <PageShell>
      <PageHeader
        icon={<ScrollText size={18} />}
        title={t('nav.contracts')}
        subtitle={t('contracts.subtitle')}
        actions={newContractButton}
      />
      <div className="ds-page">

      <div className="ds-toolbar">
        <Select suelto placeholder={false} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          aria-label={t('contractspage.filtrar_estado')} className="ctr-input ctr-input--auto">
          <option value="">{t('contracts.todos_los_estados')}</option>
          {Object.keys(STATUS_COLOR).map(v => <option key={v} value={v}>{t(`contractspage.estado_${v}`)}</option>)}
        </Select>
        <div className="ds-toolbar__spacer" />
        <div className="ds-segmented" role="group" aria-label={t('proyectos_ui.vista')}>
          {[
            { v: 'list', label: t('proyectos_ui.vista_lista'), Icon: List },
            { v: 'grid', label: t('proyectos_ui.vista_tarjetas'), Icon: LayoutGrid },
          ].map(({ v, label, Icon }) => (
            <Pulsable aria-label={label} key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)} title={label}>
              <Icon size={12} />
            </Pulsable>
          ))}
        </div>
      </div>

      {/* Banner de contratos próximos a vencer */}
      {expiring.length > 0 && (
        <div>
          {expiring.map(c => {
            const nivel = c.daysLeft <= 14 ? 'danger' : c.daysLeft <= 30 ? 'warning' : 'accent'
            return (
              <Pulsable key={c.id} type="button" className={`ctr-expiring ctr-expiring--${nivel}`}
                onClick={() => setDetail(c)}>
                <span className="ctr-expiring__icon" aria-hidden="true"><CalendarClock size={16} /></span>
                <div className="u-flex1-min0">
                  <span className="ctr-expiring__name">
                    {c.code} — {c.name}
                  </span>
                  <span className="ctr-expiring__client">
                    {c.client_name}
                  </span>
                </div>
                <div className="ctr-expiring__days">
                  {c.daysLeft === 0 ? t('contractspage.vence_hoy') : t(c.daysLeft === 1 ? 'contractspage.vence_en_uno' : 'contractspage.vence_en', { count: c.daysLeft })}
                </div>
              </Pulsable>
            )
          })}
        </div>
      )}

      {/* Stats */}
      <div className="ds-grid-stats">
        <KpiCard label={t('contractspage.kpi_total')} value={contracts.length} icon={<ScrollText size={14} />} />
        <KpiCard label={t('contractspage.kpi_activos')} value={active} accent icon={<ClipboardList size={14} />} />
        <KpiCard label={t('contractspage.kpi_valor')} value={dinero(totalValue)} icon={<Coins size={14} />} />
        <KpiCard label={t('contractspage.kpi_ots_abiertas')} value={otsAbiertas} warning={otsAbiertas > 0} icon={<Wrench size={14} />} />
      </div>

      {isLoading ? <Spinner /> : contracts.length === 0 ? (
        <EmptyState icon={<ScrollText size={28} />} title={t('contracts.no_contracts')} description={t('contractspage.crea_primer_contrato')} action={newContractButton} />
      ) : view === 'list' ? (
        <div className="ctr-table">
          <div className="ctr-table__inner">
          <div className="ctr-table__head">
            <SortableTH col="name" sort={contractSort} onSort={setContractSort}>{t('contractspage.col_contrato')}</SortableTH>
            <SortableTH col="contract_type_label" sort={contractSort} onSort={setContractSort}>{t('contractspage.col_tipo')}</SortableTH>
            <SortableTH col="total_amount" sort={contractSort} onSort={setContractSort}>{t('contractspage.dato_importe')}</SortableTH>
            <SortableTH col="start_date" sort={contractSort} onSort={setContractSort}>{t('contractspage.dato_inicio')}</SortableTH>
            <SortableTH col="end_date" sort={contractSort} onSort={setContractSort}>{t('contractspage.dato_fin')}</SortableTH>
            <span>{t('contractspage.campo_estado_corto')}</span><span>{t('contractspage.col_ots')}</span>
          </div>
          {sortedContracts.map(c => {
            const estado = estadoDe(c)
            const vencido = !!c.end_date && new Date(c.end_date) < new Date()
            return (
              <Pulsable key={c.id} type="button" className="ctr-table__row"
                onClick={() => setDetail(c)}>
                <div className="u-min0">
                  <div className="u-base-600">{c.name}</div>
                  <div className="u-text2-xs">{c.code} · {c.client_name}</div>
                </div>
                <span className="u-text2-sm">{c.contract_type_label}</span>
                <span className="ctr-amount">{importeCorto(c)}</span>
                <span className="u-text2-sm">{c.start_date ? fmtDate(c.start_date) : '—'}</span>
                <span className={vencido ? 'ctr-date is-overdue' : 'ctr-date'}>{c.end_date ? fmtDate(c.end_date) : '—'}</span>
                <span className="ctr-status-text" style={colorVar(STATUS_COLOR[estado])}>{t(`contractspage.estado_${estado}`)}</span>
                <span className="u-text2-sm">{c.work_orders?.length || 0}</span>
              </Pulsable>
            )
          })}
          </div>
        </div>
      ) : (
        <div className="ctr-grid">
          {sortedContracts.map(c => {
            const estado = estadoDe(c)
            const nOts = c.work_orders?.length ?? 0
            return (
              <Pulsable key={c.id} type="button" onClick={() => setDetail(c)}
                className="ctr-card" style={colorVar(STATUS_COLOR[estado])}>
                <div className="ctr-card__head">
                  <div className="u-min0">
                    <div className="ctr-card__code">{c.code}</div>
                    <div className="u-md-700">{c.name}</div>
                    {c.client_name && <div className="u-text2-xs-mt2 ctr-ico"><Building2 size={12} aria-hidden="true" />{c.client_name}</div>}
                  </div>
                  <span className="ctr-card__badge">{t(`contractspage.estado_${estado}`)}</span>
                </div>
                <div className="u-mb-10">
                  <span className="ctr-card__amount">{importeCorto(c)}</span>
                </div>
                <div className="ctr-card__meta">
                  {c.contract_type_label && <span className="ctr-ico"><ClipboardList size={12} aria-hidden="true" />{c.contract_type_label}</span>}
                  {nOts > 0 && <span className="ctr-ico"><Wrench size={12} aria-hidden="true" />{t(nOts === 1 ? 'contractspage.n_ot_uno' : 'contractspage.n_ots', { count: nOts })}</span>}
                </div>
                <div className="ctr-card__dates">
                  {c.start_date ? fmtDate(c.start_date) : '—'} – {c.end_date ? <span className={new Date(c.end_date) < new Date() ? 'is-overdue' : undefined}>{fmtDate(c.end_date)}</span> : '—'}
                </div>
              </Pulsable>
            )
          })}
        </div>
      )}

      {showCreate && <ContractFormModal onClose={() => setShowCreate(false)} />}
      {editing && <ContractFormModal contract={editing} onClose={() => setEditing(null)} />}
      {detail && !editing && <ContractDetail contract={detail} onClose={() => setDetail(null)} onEdit={(c) => { setDetail(null); setEditing(c) }} />}
      </div>
    </PageShell>
  )
}
