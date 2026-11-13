import { useState, useId } from 'react'
import type { CSSProperties, ChangeEvent } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { projectsApi, contractsApi } from '../services/api'
import DocumentosDeFicha from '../components/conectores/DocumentosDeFicha'
import { Button, Modal, Spinner, EmptyState, ClientSelect, useSort, SortableTH, ViewToggle } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { ScrollText } from 'lucide-react'
import { fmtCurrency, fmtDate, extractErr} from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAppT } from '../i18n/AppLangContext'
import { useFormValidation } from '../hooks/useFormValidation'
import { alpha } from '../constants/theme'
import DateInput from '../components/ui/DateInput'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

// ── Contract / WorkOrder shapes ──────────────────────────────────────────────
type WorkOrder = {
  [key: string]: unknown
  id: string
  code?: string
  name?: string
  status?: string
  amount?: number | null
  hours?: number | null
  start_date?: string | null
  end_date?: string | null
}
type Contract = {
  [key: string]: unknown
  id: string
  code?: string
  name?: string
  client_id?: string | number
  client_name?: string
  client_contact?: string
  contract_type?: string
  contract_type_label?: string
  status?: string
  total_amount?: number | null
  hourly_rate?: number | null
  hours_bag?: number | null
  hours_used?: number | null
  hours_pct?: number | null
  monthly_retainer?: number | null
  start_date?: string | null
  end_date?: string | null
  signed_date?: string | null
  payment_terms?: string | null
  notes?: string | null
  project_id?: string | number
  work_orders?: WorkOrder[]
}
type ApiErr = { response?: { data?: { detail?: string } } }


const CONTRACT_TYPES = [
  { value: 'fixed_price', label: 'Precio fijo' },
  { value: 'time_material', label: 'Tiempo y material' },
  { value: 'retainer', label: 'Retainer mensual' },
  { value: 'hourly_bag', label: 'Bolsa de horas' },
]
const STATUS_CFG: Record<string, { label: string; color: string }> = {
  draft:     { label: 'Borrador',  color: 'var(--text-2)' },
  active:    { label: 'Activo',    color: 'var(--accent)' },
  expired:   { label: 'Expirado', color: 'var(--danger)' },
  cancelled: { label: 'Cancelado', color: 'var(--text-3)' },
}
const WO_STATUS: Record<string, { label: string; color: string }> = {
  open: { label: 'Abierta', color: 'var(--accent)' },
  in_progress: { label: 'En curso', color: 'var(--warning)' },
  completed: { label: 'Completada', color: 'var(--success)' },
  invoiced: { label: 'Facturada', color: 'var(--purple)' },
}

const contractSchema = z.object({
  name: z.string().trim().min(1, 'El nombre es obligatorio'),
  project_id: z.string().trim().min(1, 'El proyecto es obligatorio'),
  client_id: z.union([z.string(), z.number()]).refine((v) => `${v}`.trim().length > 0, 'El cliente es obligatorio'),
  client_name: z.string().optional(),
  client_contact: z.string().optional(),
  contract_type: z.enum(['fixed_price', 'time_material', 'retainer', 'hourly_bag']),
  status: z.enum(['draft', 'active', 'expired', 'cancelled']),
  total_amount: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, 'El importe no puede ser negativo').optional()),
  hourly_rate: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, 'La tarifa no puede ser negativa').optional()),
  hours_bag: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, 'Las horas no pueden ser negativas').optional()),
  monthly_retainer: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, 'El retainer no puede ser negativo').optional()),
  start_date: z.string().optional(),
  end_date: z.string().optional(),
  signed_date: z.string().optional(),
  payment_terms: z.string().optional(),
  notes: z.string().optional(),
}).superRefine((values, ctx) => {
  if (values.start_date && values.end_date && values.end_date < values.start_date) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['end_date'], message: 'La fecha fin no puede ser anterior a la fecha inicio' })
  }
  if (values.contract_type === 'fixed_price' && typeof values.total_amount !== 'number') {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['total_amount'], message: 'El importe total es obligatorio para precio fijo' })
  }
  if (values.contract_type === 'time_material' && typeof values.hourly_rate !== 'number') {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['hourly_rate'], message: 'La tarifa es obligatoria para tiempo y material' })
  }
  if (values.contract_type === 'hourly_bag') {
    if (typeof values.hours_bag !== 'number') {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['hours_bag'], message: 'La bolsa de horas es obligatoria' })
    }
    if (typeof values.hourly_rate !== 'number') {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['hourly_rate'], message: 'La tarifa es obligatoria para bolsa de horas' })
    }
  }
  if (values.contract_type === 'retainer' && typeof values.monthly_retainer !== 'number') {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['monthly_retainer'], message: 'El retainer mensual es obligatorio' })
  }
})

const workOrderSchema = z.object({
  name: z.string().trim().min(1, 'El nombre de la OT es obligatorio'),
  amount: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, 'El importe no puede ser negativo').optional()),
  hours: z.preprocess((v) => (v === '' || v === null ? undefined : v), z.coerce.number().min(0, 'Las horas no pueden ser negativas').optional()),
  start_date: z.string().optional(),
  end_date: z.string().optional(),
}).superRefine((values, ctx) => {
  if (values.start_date && values.end_date && values.end_date < values.start_date) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['end_date'], message: 'La fecha fin no puede ser anterior al inicio' })
  }
})

function ContractFormModal({ contract, onClose }: { contract?: Contract | null; onClose: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const traducir = useAppT()
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
  const validation = useFormValidation(contractSchema)
  const set = (k: string) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }
  const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

  const { mutate, isPending } = useMutation({
    mutationFn: (data: Record<string, unknown>) => isEdit ? contractsApi.update(contract!.id, data) : contractsApi.create(data),
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries({ queryKey: ['contracts'] }); qc.invalidateQueries({ queryKey: ['client-detail'] }); qc.invalidateQueries({ queryKey: ['clients'] }); onClose() },
    onError: (e: ApiErr) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate(result.data as Record<string, unknown>)
  }

  return (
    <Modal open title={isEdit ? `Editar contrato` : 'Nuevo Contrato'} onClose={onClose} width={620}>
      <div className="u-grid2-14">
        <div className="u-col-full">
          <label style={ls}>Nombre *</label>
          <input value={form.name} onChange={set('name')} style={validation.inputStyle(fs, 'name')} placeholder={traducir('contracts.nombre_del_contrato')} aria-label={traducir('contracts.nombre_del_contrato')} />
          {validation.errors.name && <p className="u-field-error">{validation.errors.name}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Proyecto *</label>
          <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.project_id} onChange={set('project_id')} style={validation.inputStyle(fs, 'project_id')}>
            <option value="">Seleccionar...</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </select>
          {validation.errors.project_id && <p className="u-field-error">{validation.errors.project_id}</p>}
        </div>
        <div>
          <label style={ls}>Cliente *</label>
          <ClientSelect
            value={String(form.client_id)}
            onChange={(id, client) => {
              setForm(f => ({ ...f, client_id: id, client_name: client ? client.name : '' }))
              validation.clearFieldError('client_id')
            }}
            style={validation.inputStyle(fs, 'client_id')}
          />
          {validation.errors.client_id && <p className="u-field-error">{validation.errors.client_id}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{traducir('contracts.tipo_de_contrato')}</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.contract_type} onChange={set('contract_type')} style={validation.inputStyle(fs, 'contract_type')}>
            {CONTRACT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
          {validation.errors.contract_type && <p className="u-field-error">{validation.errors.contract_type}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>Estado</label>
          <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.status} onChange={set('status')} style={fs}>
            {Object.entries(STATUS_CFG).map(([v, c]) => <option key={v} value={v}>{c.label}</option>)}
          </select>
        </div>
        {form.contract_type === 'fixed_price' && (
          <div>
            <label style={ls}>Importe total ({fmtMoneda.simbolo})</label>
            <input type="number" value={form.total_amount} onChange={set('total_amount')} style={validation.inputStyle(fs, 'total_amount')} placeholder="Importe total" aria-label="Importe total" />
            {validation.errors.total_amount && <p className="u-field-error">{validation.errors.total_amount}</p>}
          </div>
        )}
        {form.contract_type === 'time_material' && (
          <div>
            <label style={ls}>Tarifa {fmtMoneda.simbolo}/hora</label>
            <input type="number" value={form.hourly_rate} onChange={set('hourly_rate')} style={validation.inputStyle(fs, 'hourly_rate')} placeholder={traducir('contracts.tarifa_por_hora')} aria-label={traducir('contracts.tarifa_por_hora')} />
            {validation.errors.hourly_rate && <p className="u-field-error">{validation.errors.hourly_rate}</p>}
          </div>
        )}
        {form.contract_type === 'hourly_bag' && (
          <>
            <div>
              <label style={ls}>{traducir('contracts.bolsa_de_horas')}</label>
              <input type="number" value={form.hours_bag} onChange={set('hours_bag')} style={validation.inputStyle(fs, 'hours_bag')} placeholder="Horas incluidas" aria-label="Horas incluidas" />
              {validation.errors.hours_bag && <p className="u-field-error">{validation.errors.hours_bag}</p>}
            </div>
            <div>
              <label style={ls}>Tarifa {fmtMoneda.simbolo}/hora</label>
              <input type="number" value={form.hourly_rate} onChange={set('hourly_rate')} style={validation.inputStyle(fs, 'hourly_rate')} placeholder={traducir('contracts.tarifa_por_hora')} aria-label={traducir('contracts.tarifa_por_hora')} />
              {validation.errors.hourly_rate && <p className="u-field-error">{validation.errors.hourly_rate}</p>}
            </div>
          </>
        )}
        {form.contract_type === 'retainer' && (
          <div>
            <label style={ls}>Retainer mensual ({fmtMoneda.simbolo})</label>
            <input type="number" value={form.monthly_retainer} onChange={set('monthly_retainer')} style={validation.inputStyle(fs, 'monthly_retainer')} placeholder="Importe mensual" aria-label="Importe mensual" />
            {validation.errors.monthly_retainer && <p className="u-field-error">{validation.errors.monthly_retainer}</p>}
          </div>
        )}
        <div>
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>Fecha inicio</label>
          <DateInput id={`${idCampo}-4`} value={form.start_date} onChange={set('start_date')} style={validation.inputStyle(fs, 'start_date')} />
        </div>
        <div>
          <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={ls}>Fecha fin</label>
          <DateInput id={`${idCampo}-5`} value={form.end_date} onChange={set('end_date')} style={validation.inputStyle(fs, 'end_date')} />
          {validation.errors.end_date && <p className="u-field-error">{validation.errors.end_date}</p>}
        </div>
        <div>
          <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={ls}>Fecha firma</label>
          <DateInput id={`${idCampo}-6`} value={form.signed_date} onChange={set('signed_date')} style={fs} />
        </div>
        <div>
          <label style={ls}>{traducir('contracts.condiciones_de_pago')}</label>
          <input value={form.payment_terms} onChange={set('payment_terms')} style={fs} placeholder="Ej. 30 dias fecha factura" aria-label={traducir('contracts.condiciones_de_pago')} />
        </div>
        <div className="u-col-full">
          <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} style={ls}>Notas</label>
          <textarea id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.notes} onChange={set('notes')} rows={2} style={{ ...fs, resize: 'vertical' }} />
        </div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={submit} disabled={isPending} loading={isPending}>
            {isPending ? t('common.saving') : isEdit ? t('common.save') : 'Crear contrato'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function ContractDetail({ contract, onClose, onEdit }: { contract: Contract; onClose: () => void; onEdit: (c: Contract) => void }) {
  const fmtMoneda = useFormatoMoneda()
  const traducir = useAppT()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showWO, setShowWO] = useState(false)
  const [woForm, setWoForm] = useState<Record<string, string>>({ name: '', amount: '', hours: '', start_date: '', end_date: '' })
  const woValidation = useFormValidation(workOrderSchema)
  const fs: CSSProperties = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit' }

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

  const cfg = STATUS_CFG[contract.status || ''] || STATUS_CFG.draft

  const submitWO = () => {
    const result = woValidation.validateForm(woForm)
    if (!result.success) return
    createWO(result.data as Record<string, unknown>)
  }

  return (
    <Modal open title={`${contract.code} — ${contract.name}`} onClose={onClose} width={760}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, padding: '3px 10px', borderRadius: 20, background: alpha(cfg.color, '20'), color: cfg.color, border: `1px solid ${alpha(cfg.color, '40')}`, textTransform: 'uppercase' }}>{cfg.label}</span>
        <span className="u-text2-sm">{contract.contract_type_label}</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Cliente', value: contract.client_name || '—' },
          { label: 'Importe', value: contract.total_amount ? fmtCurrency(contract.total_amount) : contract.monthly_retainer ? `${fmtCurrency(contract.monthly_retainer)}/mes` : '—' },
          { label: 'Tarifa', value: contract.hourly_rate ? `${fmtMoneda(contract.hourly_rate)}/h` : '—' },
          { label: 'Inicio', value: contract.start_date ? fmtDate(contract.start_date) : '—' },
          { label: 'Fin', value: contract.end_date ? fmtDate(contract.end_date) : '—' },
          { label: 'Firma', value: contract.signed_date ? fmtDate(contract.signed_date) : '—' },
          ...(contract.hours_bag ? [{ label: 'Bolsa horas', value: `${contract.hours_used || 0}h / ${contract.hours_bag}h (${contract.hours_pct || 0}%)` }] : []),
          ...(contract.payment_terms ? [{ label: 'Pago', value: contract.payment_terms }] : []),
        ].map(({ label, value }) => (
          <div key={label} style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px' }}>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 3 }}>{label}</div>
            <div className="u-base-600">{value}</div>
          </div>
        ))}
      </div>

      {/* Work Orders */}
      <div className="u-mb-16">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h4 style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{traducir('contracts.ordenes_de_trabajo')}{contract.work_orders?.length || 0})</h4>
          <Button size="sm" onClick={() => setShowWO(true)} icon="＋">{traducir('contracts.nueva_ot')}</Button>
        </div>
        {contract.work_orders?.length === 0 ? (
          <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', textAlign: 'center', padding: '16px 0' }}>{traducir('contracts.sin_ordenes_de_trabajo')}</div>
        ) : (
          <div className="u-stack-8">
            {contract.work_orders!.map(wo => {
              const wocfg = WO_STATUS[wo.status || ''] || WO_STATUS.open
              return (
                <div key={wo.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8 }}>
                  <div className="u-flex1">
                    <div className="u-base-600">{wo.code} — {wo.name}</div>
                    <div className="u-text2-xs">
                      {wo.amount ? fmtCurrency(wo.amount) : ''} {wo.hours ? `· ${wo.hours}h` : ''}
                      {wo.start_date ? ` · ${fmtDate(wo.start_date)}` : ''}
                    </div>
                  </div>
                  <select value={wo.status} onChange={e => updateWOStatus({ woId: wo.id, status: e.target.value })}
                    style={{ ...fs, fontSize: "var(--text-xs)", color: wocfg.color, background: alpha(wocfg.color, '15'), border: `1px solid ${alpha(wocfg.color, '40')}`, cursor: 'pointer', padding: '4px 10px' }}>
                    {Object.entries(WO_STATUS).map(([v, c]) => <option key={v} value={v}>{c.label}</option>)}
                  </select>
                </div>
              )
            })}
          </div>
        )}

        {showWO && (
          <div style={{ marginTop: 12, padding: 14, background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 'var(--radius-md)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr', gap: 10, marginBottom: 10 }}>
              <div>
                <input value={woForm.name} onChange={e => { setWoForm(f => ({ ...f, name: e.target.value })); woValidation.clearFieldError('name') }} style={woValidation.inputStyle(fs, 'name')} placeholder={traducir('contracts.nombre_de_la_orden')} aria-label={traducir('contracts.nombre_de_la_orden')} />
                {woValidation.errors.name && <p className="u-field-error">{woValidation.errors.name}</p>}
              </div>
              <div>
                <input type="number" value={woForm.amount} onChange={e => { setWoForm(f => ({ ...f, amount: e.target.value })); woValidation.clearFieldError('amount') }} style={woValidation.inputStyle(fs, 'amount')} placeholder="Importe" aria-label="Importe" />
                {woValidation.errors.amount && <p className="u-field-error">{woValidation.errors.amount}</p>}
              </div>
              <div>
                <input type="number" value={woForm.hours} onChange={e => { setWoForm(f => ({ ...f, hours: e.target.value })); woValidation.clearFieldError('hours') }} style={woValidation.inputStyle(fs, 'hours')} placeholder="Horas" aria-label="Horas" />
                {woValidation.errors.hours && <p className="u-field-error">{woValidation.errors.hours}</p>}
              </div>
              <div><DateInput value={woForm.start_date} onChange={e => { setWoForm(f => ({ ...f, start_date: e.target.value })); woValidation.clearFieldError('start_date') }} style={woValidation.inputStyle(fs, 'start_date')} /></div>
              <div>
                <DateInput value={woForm.end_date} onChange={e => { setWoForm(f => ({ ...f, end_date: e.target.value })); woValidation.clearFieldError('end_date') }} style={woValidation.inputStyle(fs, 'end_date')} />
                {woValidation.errors.end_date && <p className="u-field-error">{woValidation.errors.end_date}</p>}
              </div>
            </div>
            <div className="u-row-8">
              <Button size="sm" onClick={submitWO}>Crear OT</Button>
              <Button size="sm" variant="secondary" onClick={() => setShowWO(false)}>{t('common.cancel')}</Button>
            </div>
          </div>
        )}
      </div>

      {/* Revisión 2026-11: el contrato firmado y sus anexos viven en contecmind, con versiones y aprobación. */}
      <div className="u-mb-20"><DocumentosDeFicha ficha="contract" id={contract.id} preguntar /></div>

      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>Cerrar</Button>
        <Button onClick={() => { onClose(); onEdit(contract) }}>✏️ Editar</Button>
      </div>
    </Modal>
  )
}

export default function ContractsPage(): JSX.Element {
  const traducir = useAppT()
  const t = useAppT()
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<Contract | null>(null)
  const [detail, setDetail] = useState<Contract | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [view, setView] = useState('list')

  const { data: contracts = [], isLoading } = useQuery<Contract[]>({
    queryKey: ['contracts', statusFilter],
    queryFn: () => contractsApi.list(statusFilter ? { status: statusFilter } : {}).then((r: { data: unknown }) => ((r.data as { items?: Contract[] })?.items ?? (r.data as Contract[]) ?? [])),
  })

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

  return (
    <PageShell>
      <PageHeader
        icon={<ScrollText size={18} />}
        title={t('contracts.title')}
        subtitle={t('contracts.subtitle')}
        actions={
          <div className="u-wrap-10">
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
              style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
              <option value="">{traducir('contracts.todos_los_estados')}</option>
              {Object.entries(STATUS_CFG).map(([v, c]) => <option key={v} value={v}>{c.label}</option>)}
            </select>
            <ViewToggle view={view} onChange={setView} />
            <Button onClick={() => setShowCreate(true)} icon="＋">{traducir('contracts.new_contract')}</Button>
          </div>
        }
      />

      {/* Banner de contratos próximos a vencer */}
      {expiring.length > 0 && (
        <div className="u-mb-20">
          {expiring.map(c => {
            const color = c.daysLeft <= 14 ? 'var(--danger)' : c.daysLeft <= 30 ? 'var(--warning)' : 'var(--accent)'
            const bg    = c.daysLeft <= 14 ? 'var(--danger-bg)' : c.daysLeft <= 30 ? 'var(--warning-bg)' : 'var(--accent-muted)'
            const bdr   = c.daysLeft <= 14 ? 'var(--danger-border)' : c.daysLeft <= 30 ? 'var(--warning-border)' : 'var(--accent-border)'
            const icon  = c.daysLeft <= 14 ? '🔴' : c.daysLeft <= 30 ? '🟡' : '🔵'
            return (
              <button key={c.id} type="button" style={{ display: 'flex', alignItems: 'center', gap: 12,
                padding: '10px 16px', background: bg, border: `1px solid ${bdr}`,
                borderRadius: 'var(--radius-md)', marginBottom: 6, cursor: 'pointer', width: '100%', textAlign: 'left', fontFamily: 'inherit' }}
                onClick={() => setDetail(c)}>
                <span style={{ fontSize: "var(--text-lg)" }}>{icon}</span>
                <div className="u-flex1-min0">
                  <span style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)' }}>
                    {c.code} — {c.name}
                  </span>
                  <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginLeft: 10 }}>
                    {c.client_name}
                  </span>
                </div>
                <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color, whiteSpace: 'nowrap' }}>
                  {c.daysLeft === 0 ? 'Vence hoy' : `Vence en ${c.daysLeft} día${c.daysLeft > 1 ? 's' : ''}`}
                </div>
              </button>
            )
          })}
        </div>
      )}

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(150px, 100%), 1fr))', gap: 14, marginBottom: 24 }}>
        {[
          { label: 'Total contratos', value: contracts.length, color: 'var(--text-2)' },
          { label: 'Activos', value: active, color: 'var(--accent)' },
          { label: 'Valor total', value: fmtCurrency(totalValue), color: 'var(--success)' },
          { label: 'OTs abiertas', value: contracts.reduce((s, c) => s + (c.work_orders?.filter(w => w.status === 'open').length || 0), 0), color: 'var(--warning)' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '14px 18px', minWidth: 0 }}>
            <div style={{ fontSize: "var(--text-xl)", fontWeight: 800, fontFamily: 'var(--font-mono)', color }}>{value}</div>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
          </div>
        ))}
      </div>

      {isLoading ? <Spinner /> : contracts.length === 0 ? (
        <EmptyState icon="📄" title={traducir('contracts.no_contracts')} description="Crea el primer contrato para este entorno" />
      ) : view === 'list' ? (
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflowX: 'auto' }}>
          <div style={{ minWidth: 760 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 80px 80px', gap: 16, padding: '10px 20px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
            <SortableTH col="name" sort={contractSort} onSort={setContractSort}>Contrato</SortableTH>
            <SortableTH col="contract_type_label" sort={contractSort} onSort={setContractSort}>Tipo</SortableTH>
            <SortableTH col="total_amount" sort={contractSort} onSort={setContractSort}>Importe</SortableTH>
            <SortableTH col="start_date" sort={contractSort} onSort={setContractSort}>Inicio</SortableTH>
            <SortableTH col="end_date" sort={contractSort} onSort={setContractSort}>Fin</SortableTH>
            <span>Estado</span><span>OTs</span>
          </div>
          {sortedContracts.map(c => {
            const cfg = STATUS_CFG[c.status || ''] || STATUS_CFG.draft
            return (
              <button key={c.id} type="button" style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 80px 80px', gap: 16, padding: '12px 20px', borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)', alignItems: 'center', cursor: 'pointer', width: '100%', textAlign: 'left', background: 'transparent', border: 'none', fontFamily: 'inherit' }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                onClick={() => setDetail(c)}>
                <div>
                  <div className="u-base-600">{c.name}</div>
                  <div className="u-text2-xs">{c.code} · {c.client_name}</div>
                </div>
                <span className="u-text2-sm">{c.contract_type_label}</span>
                <span style={{ fontSize: "var(--text-sm)", fontFamily: 'var(--font-mono)' }}>
                  {c.total_amount ? fmtCurrency(c.total_amount) : c.monthly_retainer ? `${fmtCurrency(c.monthly_retainer)}/m` : c.hours_bag ? `${c.hours_bag}h` : '—'}
                </span>
                <span className="u-text2-sm">{c.start_date ? fmtDate(c.start_date) : '—'}</span>
                <span style={{ fontSize: "var(--text-sm)", color: c.end_date && new Date(c.end_date) < new Date() ? 'var(--danger)' : 'var(--text-2)' }}>{c.end_date ? fmtDate(c.end_date) : '—'}</span>
                <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: cfg.color }}>{cfg.label}</span>
                <span className="u-text2-sm">{c.work_orders?.length || 0}</span>
              </button>
            )
          })}
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(320px, 100%), 1fr))', gap: 14 }}>
          {sortedContracts.map(c => {
            const cfg = STATUS_CFG[c.status || ''] || STATUS_CFG.draft
            return (
              <button key={c.id} type="button" onClick={() => setDetail(c)}
                style={{ background: 'var(--surface-2)', border: `1px solid ${alpha(cfg.color, '30')}`, borderRadius: 12, padding: '16px 20px', cursor: 'pointer', transition: 'border-color 0.15s' }}
                onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-glow)'}
                onMouseLeave={e => e.currentTarget.style.borderColor = alpha(cfg.color, '30')}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, marginBottom: 8 }}>
                  <div className="u-min0">
                    <div style={{ fontSize: "var(--text-xs)", fontFamily: 'var(--font-mono)', color: 'var(--text-2)', marginBottom: 2 }}>{c.code}</div>
                    <div className="u-md-700">{c.name}</div>
                    {c.client_name && <div className="u-text2-xs-mt2">🏢 {c.client_name}</div>}
                  </div>
                  <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, padding: '3px 9px', borderRadius: 20, background: alpha(cfg.color, '20'), color: cfg.color, whiteSpace: 'nowrap', flexShrink: 0 }}>{cfg.label}</span>
                </div>
                <div className="u-mb-10">
                  <span style={{ fontSize: "var(--text-xl)", fontWeight: 800, fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>
                    {c.total_amount ? fmtCurrency(c.total_amount) : c.monthly_retainer ? `${fmtCurrency(c.monthly_retainer)}/m` : c.hours_bag ? `${c.hours_bag}h` : '—'}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 12, fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 8 }}>
                  {c.contract_type_label && <span>📋 {c.contract_type_label}</span>}
                  {(c.work_orders?.length ?? 0) > 0 && <span>🔧 {c.work_orders!.length} OT{c.work_orders!.length !== 1 ? 's' : ''}</span>}
                </div>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', borderTop: '1px solid var(--surface-4)', paddingTop: 8 }}>
                  {c.start_date ? fmtDate(c.start_date) : '—'} → {c.end_date ? <span style={{ color: new Date(c.end_date) < new Date() ? 'var(--danger)' : 'inherit' }}>{fmtDate(c.end_date)}</span> : '—'}
                </div>
              </button>
            )
          })}
        </div>
      )}

      {showCreate && <ContractFormModal onClose={() => setShowCreate(false)} />}
      {editing && <ContractFormModal contract={editing} onClose={() => setEditing(null)} />}
      {detail && !editing && <ContractDetail contract={detail} onClose={() => setDetail(null)} onEdit={(c) => { setDetail(null); setEditing(c) }} />}
    </PageShell>
  )
}