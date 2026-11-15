import { CSSProperties, useState, useId, useMemo } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { rateCardsApi } from '../services/api'
import type { TablaDeTarifas, TarifaAplicaA, TarifaEntrada } from '../services/api/tipos-finanzas'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Tag } from 'lucide-react'
import { Button, Modal, EmptyState } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { z } from 'zod'
import { useFormValidation } from '../hooks/useFormValidation'
import DateInput from '../components/ui/DateInput'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import './RateCardsPage.css'
type AppliesTo = TarifaAplicaA
type RateEntry = TarifaEntrada
type RateTable = TablaDeTarifas

type EntryFormState = {
  label: string
  billing_rate: string
  cost_rate: string
  escalation_pct: string
  valid_from: string
  valid_to: string
  notes: string
}

type RateTableCreateForm = {
  name: string
  description: string
  applies_to: AppliesTo
  is_default: boolean
}


type Traductor = ReturnType<typeof useAppT>

const makeRateEntrySchema = (t: Traductor) => {
const optionalPositive = z.union([z.literal(''), z.coerce.number().nonnegative(t('tarifas_ui.debe_ser_positivo'))]).optional()
const optionalDate = z.union([z.literal(''), z.string().regex(/^\d{4}-\d{2}-\d{2}$/, t('tarifas_ui.fecha_invalida'))]).optional()

return z.object({
  label: z.string().trim().min(1, t('tarifas_ui.rol_obligatorio')).max(120, t('tarifas_ui.maximo_n', { n: 120 })),
  billing_rate: optionalPositive,
  cost_rate: optionalPositive,
  escalation_pct: z.coerce.number().min(0, t('tarifas_ui.no_negativo')).max(100, t('tarifas_ui.maximo_100')),
  valid_from: optionalDate,
  valid_to: optionalDate,
  notes: z.string().max(500, t('tarifas_ui.maximo_n', { n: 500 })).optional(),
}).refine(d => {
  if (!d.valid_from || !d.valid_to) return true
  return d.valid_from <= d.valid_to
}, { message: t('tarifas_ui.fin_posterior'), path: ['valid_to'] })
}

const makeRateTableSchema = (t: Traductor) => z.object({
  name: z.string().trim().min(1, t('tarifas_ui.nombre_obligatorio')).max(120, t('tarifas_ui.maximo_n', { n: 120 })),
  description: z.string().max(500, t('tarifas_ui.maximo_n', { n: 500 })).optional(),
  applies_to: z.enum(['role', 'department', 'client']),
  is_default: z.boolean().optional(),
})

// ── Formulario de entrada ─────────────────────────────────────────────────────
function EntryForm({ tableId, entry, onClose }: { tableId: string | number; entry?: RateEntry | null; onClose: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const traducir = useAppT()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const isEdit = !!entry?.id
  const [form, setForm] = useState<EntryFormState>({
    label:          entry?.label          || '',
    billing_rate:   String(entry?.billing_rate ?? ''),
    cost_rate:      String(entry?.cost_rate ?? ''),
    escalation_pct: String(entry?.escalation_pct ?? 0),
    valid_from:     entry?.valid_from     || '',
    valid_to:       entry?.valid_to       || '',
    notes:          entry?.notes          || '',
  })
  const validation = useFormValidation(useMemo(() => makeRateEntrySchema(t), [t]))

  const { mutate, isPending } = useMutation({
    mutationFn: (d: Record<string, unknown>) => isEdit && entry
      ? rateCardsApi.updateEntry(tableId, entry.id, d)
      : rateCardsApi.addEntry(tableId, d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rate-card', tableId] })
      toast.success(isEdit ? t('tarifas_ui.entrada_actualizada') : t('tarifas_ui.entrada_anadida'))
      onClose()
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const save = () => {
    const result = validation.validateForm(form)
    if (!result.success || !result.data) return
    mutate({
      ...result.data,
      billing_rate:   result.data.billing_rate === '' || result.data.billing_rate == null ? null : Number(result.data.billing_rate),
      cost_rate:      result.data.cost_rate === '' || result.data.cost_rate == null ? null : Number(result.data.cost_rate),
      escalation_pct: Number(result.data.escalation_pct),
    })
  }

  return (
    <Modal open title={isEdit ? t('tarifas_ui.editar_tarifa') : t('tarifas_ui.nueva_tarifa')} onClose={onClose} width={500}>
      <div className="rc-grid">
        <div className="u-col-full">
          <label className="rc-lbl" id={`${idCampo}-rol-et`} htmlFor={`${idCampo}-rol`}>{t('tarifas_ui.rol_perfil_req')}</label>
          <input className="rc-inp" id={`${idCampo}-rol`} aria-labelledby={`${idCampo}-rol-et`} value={form.label} onChange={e => setForm(f=>({...f,label:e.target.value}))} placeholder={t('tarifas_ui.rol_perfil')} />
        </div>
        <div>
          <label className="rc-lbl">{traducir('ratecards.tarifa_facturacion_h')}</label>
          <input className="rc-inp" type="number" value={form.billing_rate} onChange={e => setForm(f=>({...f,billing_rate:e.target.value}))} placeholder={t('tarifas_ui.tarifa_facturacion')} aria-label={traducir('ratecards.tarifa_de_facturacion')} />
        </div>
        <div>
          <label className="rc-lbl">{t('tarifas_ui.coste_interno_moneda', { moneda: fmtMoneda.simbolo })}</label>
          <input className="rc-inp" type="number" value={form.cost_rate} onChange={e => setForm(f=>({...f,cost_rate:e.target.value}))} placeholder={t('tarifas_ui.coste_interno')} aria-label={t('tarifas_ui.coste_interno')} />
        </div>
        <div>
          <label className="rc-lbl" id={`${idCampo}-escalado-et`} htmlFor={`${idCampo}-escalado`}>{t('tarifas_ui.escalado_anual_pct')}</label>
          <input className="rc-inp" id={`${idCampo}-escalado`} aria-labelledby={`${idCampo}-escalado-et`} type="number" value={form.escalation_pct} onChange={e => setForm(f=>({...f,escalation_pct:e.target.value}))} placeholder={t('tarifas_ui.pct_anual')} min="0" max="20" step="0.5" />
        </div>
        <div>
          <label className="rc-lbl" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{traducir('ratecards.valido_desde')}</label>
          <DateInput id={`${idCampo}-1`} value={form.valid_from} onChange={e => setForm(f=>({...f,valid_from:e.target.value}))} className="rc-inp" />
        </div>
        <div>
          <label className="rc-lbl" id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`}>{traducir('ratecards.valido_hasta')}</label>
          <DateInput id={`${idCampo}-2`} value={form.valid_to} onChange={e => setForm(f=>({...f,valid_to:e.target.value}))} className="rc-inp" />
        </div>
        <div className="u-col-full">
          <label className="rc-lbl" id={`${idCampo}-notas-et`} htmlFor={`${idCampo}-notas`}>{t('tarifas_ui.notas')}</label>
          <input className="rc-inp" id={`${idCampo}-notas`} aria-labelledby={`${idCampo}-notas-et`} value={form.notes} onChange={e => setForm(f=>({...f,notes:e.target.value}))} placeholder={t('tarifas_ui.notas_internas')} />
        </div>
      </div>

      {Number(form.billing_rate) > 0 && Number(form.cost_rate) > 0 && (
        <div className="rc-card-success">
          {t('tarifas_ui.margen')} <strong>{Math.round((1 - Number(form.cost_rate) / Number(form.billing_rate)) * 100)}%</strong>
          {Number(form.escalation_pct) > 0 && t('tarifas_ui.tarifa_en_un_ano', { importe: fmtMoneda(Math.round(Number(form.billing_rate) * (1 + Number(form.escalation_pct)/100))) })}
        </div>
      )}

      <div className="u-actions-8">
        <button onClick={onClose} className="u-btn-outline-sm">{t('common.cancel')}</button>
        <Button onClick={save} loading={isPending} disabled={!form.label || isPending}>
          {isEdit ? t('tarifas_ui.guardar') : t('tarifas_ui.anadir')}
        </Button>
      </div>
    </Modal>
  )
}

// ── Detalle de tabla ──────────────────────────────────────────────────────────
function RateTableDetail({ tableId, onBack }: { tableId: string | number; onBack: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const traducir = useAppT()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showEntry, setShowEntry]   = useState(false)
  const [editEntry, setEditEntry]   = useState<RateEntry | null>(null)
  const [showDupe, setShowDupe]     = useState(false)
  const [dupeEsc, setDupeEsc]       = useState(3)

  const { data: table, isLoading } = useQuery<RateTable>({
    queryKey: ['rate-card', tableId],
    queryFn: () => rateCardsApi.get(tableId).then(r => r.data),
  })

  const { mutate: deleteEntry } = useMutation({
    mutationFn: (eid: string | number) => rateCardsApi.deleteEntry(tableId, eid),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rate-card', tableId] }); toast.success(t('tarifas_ui.entrada_eliminada')) },

    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const { mutate: duplicate, isPending: duping } = useMutation({
    mutationFn: () => rateCardsApi.duplicate(tableId, { escalation_pct: dupeEsc }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rate-cards'] }); toast.success(t('tarifas_ui.tabla_duplicada')); setShowDupe(false); onBack() },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (isLoading) return <div className="rc-state-muted">{t('common.loading')}</div>
  if (!table) return null

  const entries = table.entries || []
  const marginEntries = entries.filter((e: RateEntry) => e.billing_rate && e.cost_rate)
  const avgMargin = marginEntries.length > 0
    ? Math.round(marginEntries
        .reduce((s: number, e: RateEntry) => s + (1 - Number(e.cost_rate) / Number(e.billing_rate)), 0)
        / marginEntries.length * 100)
    : null

  return (
    <div>
      <div className="rc-row">
        <button className="rc-btn-ghost-sm" onClick={onBack}>
          {t('tarifas_ui.volver')}
        </button>
        <div className="u-flex1">
          <div className="rc-text-lg-em-strong">{table.name}</div>
          {table.description && <div className="u-text2-sm">{table.description}</div>}
        </div>
        {avgMargin !== null && (
          <div className="rc-card-success-2">
            {t('tarifas_ui.margen_medio', { n: avgMargin })}
          </div>
        )}
        <button className="rc-btn-ghost-sm-2" onClick={() => setShowDupe(true)}>
          {traducir('ratecards.duplicar_con_escalado')}
        </button>
        <Button onClick={() => setShowEntry(true)}>{traducir('ratecards.nueva_tarifa')}</Button>
      </div>

      {entries.length === 0 ? (
        <EmptyState icon="💰" title={traducir('ratecards.sin_tarifas')} description={t('tarifas_ui.sin_tarifas_desc')} />
      ) : (
        <div className="rc-panel rc-box">
          <table className="u-table">
            <thead>
              <tr className="u-border-b">
                {[t('tarifas_ui.rol_perfil'), t('tarifas_ui.col_facturacion'), t('tarifas_ui.col_coste'), t('tarifas_ui.col_margen'), t('tarifas_ui.col_escalado'), t('tarifas_ui.col_vigencia'), ''].map(h => (
                  <th className="rc-th" key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => {
                const margin = e.billing_rate && e.cost_rate
                  ? Math.round((1 - Number(e.cost_rate) / Number(e.billing_rate)) * 100) : null
                return (
                  <tr className="rc-tr" key={e.id} style={{ '--rc-tr-background': i % 2 === 0 ? 'transparent' : 'color-mix(in srgb, var(--text-1) 3%, transparent)' } as CSSProperties}>
                    <td className="rc-td-base">{e.label}</td>
                    <td className="rc-td-accent-base-strong-mono">
                      {e.billing_rate ? `${fmtMoneda(e.billing_rate)}/h` : '—'}
                    </td>
                    <td className="rc-td-muted-base-mono">
                      {e.cost_rate ? `${fmtMoneda(e.cost_rate)}/h` : '—'}
                    </td>
                    <td className="rc-td">
                      {margin !== null && (
                        <span className="rc-text-sm-strong" style={{ '--rc-text-sm-strong-color': margin > 50 ? 'var(--success)' : margin > 30 ? 'var(--warning)' : 'var(--danger)' } as CSSProperties}>
                          {margin}%
                        </span>
                      )}
                    </td>
                    <td className="rc-td-muted-xs">
                      {(e.escalation_pct ?? 0) > 0 ? t('tarifas_ui.pct_anio', { n: e.escalation_pct ?? 0 }) : '—'}
                    </td>
                    <td className="rc-td-muted-xs">
                      {e.valid_from || e.valid_to ? `${e.valid_from || '?'} → ${e.valid_to || '∞'}` : '—'}
                    </td>
                    <td className="rc-td">
                      <div className="u-row-6">
                        <button className="rc-btn-ghost-accent-xs" aria-label={t('common.edit')} title={t('common.edit')} onClick={() => setEditEntry(e)}>✏️</button>
                        <button className="rc-btn-ghost-danger-xs" aria-label={t('common.delete')} title={t('common.delete')} onClick={() => { openConfirmGlobal({ message: t('tarifas_ui.eliminar_tarifa_confirm', { nombre: e.label }), onConfirm: () => deleteEntry(e.id), danger: true }) }}>🗑</button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {(showEntry || editEntry) && (
        <EntryForm tableId={tableId} entry={editEntry} onClose={() => { setShowEntry(false); setEditEntry(null) }} />
      )}

      {showDupe && (
        <Modal open title={traducir('ratecards.duplicar_tabla_con_escalado')} onClose={() => setShowDupe(false)} width={420}>
          <div className="u-mb-16">
            <label className="rc-lbl" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{t('tarifas_ui.escalado_anual_pct')}</label>
            <input className="rc-inp" id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} type="number" value={dupeEsc} onChange={e => setDupeEsc(+e.target.value)} min="0" max="20" step="0.5" />
            <div className="rc-text-muted-xs">
              {traducir('ratecards.copia_con_incremento', { nombre: table.name })}
            </div>
          </div>
          <div className="u-actions-8">
            <button onClick={() => setShowDupe(false)} className="u-btn-outline-sm">{t('common.cancel')}</button>
            <Button onClick={() => duplicate()} loading={duping}>{t('tarifas_ui.duplicar_pct', { n: dupeEsc })}</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
export default function RateCardsPage() {
  const idCampo = useId()
  const traducir = useAppT()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selected, setSelected]   = useState<string | number | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm]           = useState<RateTableCreateForm>({ name: '', description: '', applies_to: 'role', is_default: false })

  // Auditoría 2026-08 (P1-6): `rateTableSchema` estaba definido con sus reglas
  // (trim, máx. 120 / 500 caracteres) y NO se usaba en ninguna parte — lo delató
  // ESLint al poder leer TypeScript por primera vez. El formulario enviaba
  // `create(form)` directo con `disabled={!form.name}` como única comprobación,
  // así que aceptaba nombres sin recortar y descripciones de cualquier longitud.
  // Se conecta con el mismo patrón que ya usa EntryForm con rateEntrySchema.
  const tableValidation = useFormValidation(useMemo(() => makeRateTableSchema(t), [t]))

  const { data: tables = [], isLoading } = useQuery<RateTable[]>({
    queryKey: ['rate-cards'],
    queryFn: () => rateCardsApi.list().then(r => r.data),
  })

  const { mutate: create, isPending } = useMutation({
    mutationFn: rateCardsApi.create,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['rate-cards'] })
      setShowCreate(false)
      setForm({ name: '', description: '', applies_to: 'role', is_default: false })
      if (res?.data?.id != null) setSelected(res.data.id)
      toast.success(t('tarifas_ui.tabla_creada'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const createTable = () => {
    const result = tableValidation.validateForm(form)
    if (!result.success || !result.data) return
    create(result.data)
  }

  const { mutate: del } = useMutation({
    mutationFn: rateCardsApi.delete,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rate-cards'] }); toast.success(t('tarifas_ui.tabla_eliminada')) },

    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  if (selected) return <RateTableDetail tableId={selected} onBack={() => setSelected(null)} />

  return (
    <PageShell>
      <PageHeader icon={<Tag size={18} />} title={t('rate_cards.title')} subtitle={t('rate_cards.subtitle')} />

      <div className="rc-row-2">
        <Button onClick={() => setShowCreate(true)}>{traducir('ratecards.nueva_tabla_de_tarifas')}</Button>
      </div>

      {isLoading ? (
        <div className="rc-state-muted-2">{t('common.loading')}</div>
      ) : tables.length === 0 ? (
        <EmptyState icon="💰" title={traducir('ratecards.sin_tablas_de_tarifas')} description={t('tarifas_ui.sin_tablas_desc')} />
      ) : (
        <div className="rc-grid-2">
          {tables.map(tabla => (
            <button className="rc-btn" key={tabla.id} type="button" style={{ '--rc-btn-border': `1px solid ${tabla.is_default ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}
              onClick={() => setSelected(tabla.id)}
            >
              <div className="rc-row-3">
                <div className="rc-text-md-em">{tabla.name}</div>
                <div className="rc-row-4">
                  {tabla.is_default && (
                    <span className="rc-card-accent">{t('tarifas_ui.por_defecto')}</span>
                  )}
                  <span className="rc-card-muted">
                    {tabla.applies_to === 'role' ? traducir('ratecards.por_rol_perfil') : tabla.applies_to === 'department' ? traducir('ratecards.por_departamento') : tabla.applies_to === 'client' ? traducir('ratecards.por_cliente') : tabla.applies_to}
                  </span>
                </div>
              </div>
              {tabla.description && <div className="rc-text-muted-sm">{tabla.description}</div>}
              <div className="u-text2-sm">
                {tabla.entry_count === 1 ? t('tarifas_ui.una_tarifa') : t('tarifas_ui.n_tarifas', { n: tabla.entry_count || 0 })}
              </div>
              <div className="rc-row-5">
                <button className="rc-btn-ghost-danger-xs" type="button" aria-label={t('tarifas_ui.eliminar_tabla')} title={t('tarifas_ui.eliminar_tabla')} onClick={e => { e.stopPropagation(); openConfirmGlobal({message: t('tarifas_ui.eliminar_tabla_confirm', { nombre: tabla.name }), onConfirm: () => del(tabla.id),danger:true}) }}>
                  🗑
                </button>
              </div>
            </button>
          ))}
        </div>
      )}

      {showCreate && (
        <Modal open title={traducir('ratecards.nueva_tabla_de_tarifas_2')} onClose={() => setShowCreate(false)} width={480}>
          <div className="rc-stack">
            <div>
              <label className="rc-lbl" id={`${idCampo}-nombre-et`} htmlFor={`${idCampo}-nombre`}>{t('tarifas_ui.nombre_req')}</label>
              <input className="rc-inp" id={`${idCampo}-nombre`} aria-labelledby={`${idCampo}-nombre-et`} value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} placeholder={traducir('ratecards.nombre_de_la_tabla')} aria-label={traducir('ratecards.nombre_de_la_tabla')} />
            </div>
            <div>
              <label className="rc-lbl">{traducir('ratecards.descripcion')}</label>
              <input className="rc-inp" value={form.description} onChange={e => setForm(f=>({...f,description:e.target.value}))} placeholder={t('tarifas_ui.descripcion_opcional')} aria-label={t('tarifas_ui.descripcion_opcional')} />
            </div>
            <div>
              <label className="rc-lbl" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{t('tarifas_ui.aplicar_a')}</label>
              <select className="rc-inp" id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.applies_to} onChange={e => setForm(f=>({...f,applies_to:e.target.value as AppliesTo}))}>
                <option value="role">{traducir('ratecards.por_rol_perfil')}</option>
                <option value="department">{traducir('ratecards.por_departamento')}</option>
                <option value="client">{traducir('ratecards.por_cliente')}</option>
              </select>
            </div>
            <label className="rc-label-sm">
              <input className="rc-input" type="checkbox" aria-label={traducir('ratecards.tabla_por_defecto_se_usa_cuando_no')} checked={form.is_default} onChange={e => setForm(f=>({...f,is_default:e.target.checked}))} />
              {traducir('ratecards.tabla_por_defecto_se_usa_cuando_no')}
            </label>
          </div>
          <div className="u-actions-8">
            <button onClick={() => setShowCreate(false)} className="u-btn-outline-sm">{t('common.cancel')}</button>
            <Button onClick={createTable} loading={isPending} disabled={!form.name || isPending}>{t('tarifas_ui.crear_tabla')}</Button>
          </div>
        </Modal>
      )}
    </PageShell>
  )
}
