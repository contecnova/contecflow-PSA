/**
 * RateCardsPage — tablas de tarifas por rol, departamento o cliente (/rate-cards).
 *
 * 16-11-2026: pasada de diseño. Título «Tarifas» (el del menú; antes «Rate
 * Cards»); «Nueva tabla de tarifas» a la cabecera con icono (antes en el
 * cuerpo con «+ »); el detalle de una tabla salía sin cabecera de página ni
 * márgenes: ahora PageShell + PageHeader con «Volver». Vacíos con icono lucide
 * (antes emojis); acciones con iconos lucide (antes emojis); campos y botones
 * del kit (antes grises y botones propios); la tarjeta de tabla era un botón
 * con otro botón dentro (HTML no válido); vigencia con el formateador de fechas.
 */
import { useState, useMemo } from 'react'
import type { CSSProperties, KeyboardEvent } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, fmtDate } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { rateCardsApi } from '../services/api'
import type { TablaDeTarifas, TarifaAplicaA, TarifaEntrada } from '../services/api/tipos-finanzas'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Tag, Plus, ArrowLeft, Copy, Pencil, Trash2, Check, Coins, Table2 } from 'lucide-react'
import { Button, Card, EmptyState, Input, Modal, Select, Spinner, Checkbox, Pulsable, TablaSimple, useErroresDeCampo } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
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

function etiquetaAmbito(t: Traductor, a: string) {
  return a === 'role' ? t('ratecards.por_rol_perfil') : a === 'department' ? t('ratecards.por_departamento') : a === 'client' ? t('ratecards.por_cliente') : a
}

// ── Formulario de entrada ─────────────────────────────────────────────────────
function EntryForm({ tableId, entry, onClose }: { tableId: string | number; entry?: RateEntry | null; onClose: () => void }) {
  const fmtMoneda = useFormatoMoneda()
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

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: (d: Record<string, unknown>) => isEdit && entry
      ? rateCardsApi.updateEntry(tableId, entry.id, d)
      : rateCardsApi.addEntry(tableId, d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rate-card', tableId] })
      toast.success(isEdit ? t('tarifas_ui.entrada_actualizada') : t('tarifas_ui.entrada_anadida'))
      onClose()
    },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
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
    <Modal open title={isEdit ? t('tarifas_ui.editar_tarifa') : t('tarifas_ui.nueva_tarifa')} onClose={onClose} width={520}>
      <div className="u-stack-16">
        <div className="rc-grid">
          <div className="u-col-full">
            <Input error={campos.de('label')} label={t('tarifas_ui.rol_perfil_req')} value={form.label} onChange={e => setForm(f=>({...f,label:e.target.value}))} placeholder={t('tarifas_ui.rol_perfil')} />
          </div>
          <Input error={campos.de('billing_rate')} label={t('tarifas_ui.facturacion_moneda', { moneda: fmtMoneda.simbolo })} type="number" value={form.billing_rate} onChange={e => setForm(f=>({...f,billing_rate:e.target.value}))} />
          <Input error={campos.de('cost_rate')} label={t('tarifas_ui.coste_interno_moneda', { moneda: fmtMoneda.simbolo })} type="number" value={form.cost_rate} onChange={e => setForm(f=>({...f,cost_rate:e.target.value}))} />
          <Input error={campos.de('escalation_pct')} label={t('tarifas_ui.escalado_anual_pct')} type="number" value={form.escalation_pct} onChange={e => setForm(f=>({...f,escalation_pct:e.target.value}))} />
          <div />
          <div className="ui-field">
            <label className="uiinde-estiloetiqueta" htmlFor="rc-desde">{t('ratecards.valido_desde')}</label>
            <DateInput id="rc-desde" value={form.valid_from} onChange={e => setForm(f=>({...f,valid_from:e.target.value}))} className="ds-input" />{msg('valid_from')}
          </div>
          <div className="ui-field">
            <label className="uiinde-estiloetiqueta" htmlFor="rc-hasta">{t('ratecards.valido_hasta')}</label>
            <DateInput id="rc-hasta" value={form.valid_to} onChange={e => setForm(f=>({...f,valid_to:e.target.value}))} className="ds-input" />{msg('valid_to')}
          </div>
          <div className="u-col-full">
            <Input error={campos.de('notes')} label={t('tarifas_ui.notas')} value={form.notes} onChange={e => setForm(f=>({...f,notes:e.target.value}))} placeholder={t('tarifas_ui.notas_internas')} />
          </div>
        </div>

        {Number(form.billing_rate) > 0 && Number(form.cost_rate) > 0 && (
          <div className="rc-aviso-margen">
            <Coins size={14} aria-hidden />
            <span>
              {t('tarifas_ui.margen')} <strong>{Math.round((1 - Number(form.cost_rate) / Number(form.billing_rate)) * 100)}%</strong>
              {Number(form.escalation_pct) > 0 && t('tarifas_ui.tarifa_en_un_ano', { importe: fmtMoneda(Math.round(Number(form.billing_rate) * (1 + Number(form.escalation_pct)/100))) })}
            </span>
          </div>
        )}

        <div className="rc-acciones">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button icon={isEdit ? <Check size={14} /> : <Plus size={14} />} onClick={save} loading={isPending} disabled={!form.label}>
            {isEdit ? t('tarifas_ui.guardar') : t('tarifas_ui.anadir')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Detalle de tabla ──────────────────────────────────────────────────────────
function RateTableDetail({ tableId, onBack }: { tableId: string | number; onBack: () => void }) {
  const fmtMoneda = useFormatoMoneda()
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

  const volver = <Button variant="secondary" icon={<ArrowLeft size={14} />} onClick={onBack}>{t('tarifas_ui.volver')}</Button>

  if (isLoading || !table) return (
    <PageShell>
      <PageHeader icon={<Tag size={18} />} title={t('nav.rate_cards')} actions={volver} showListExport={false} />
      {isLoading && <div className="rc-cargando"><Spinner /></div>}
    </PageShell>
  )

  const entries = table.entries || []
  const marginEntries = entries.filter((e: RateEntry) => e.billing_rate && e.cost_rate)
  const avgMargin = marginEntries.length > 0
    ? Math.round(marginEntries
        .reduce((s: number, e: RateEntry) => s + (1 - Number(e.cost_rate) / Number(e.billing_rate)), 0)
        / marginEntries.length * 100)
    : null

  const vigencia = (e: RateEntry) => {
    if (!e.valid_from && !e.valid_to) return '—'
    const desde = e.valid_from ? fmtDate(e.valid_from) : t('tarifas_ui.sin_inicio')
    const hasta = e.valid_to ? fmtDate(e.valid_to) : t('tarifas_ui.sin_fin')
    return `${desde} – ${hasta}`
  }

  return (
    <PageShell>
      <PageHeader
        icon={<Tag size={18} />}
        title={table.name}
        subtitle={table.description || etiquetaAmbito(t, table.applies_to)}
        showListExport={false}
        actions={
          <div className="u-wrap-8">
            {volver}
            <Button variant="secondary" icon={<Copy size={14} />} onClick={() => setShowDupe(true)}>{t('ratecards.duplicar_con_escalado')}</Button>
            <Button icon={<Plus size={14} />} onClick={() => setShowEntry(true)}>{t('ratecards.nueva_tarifa')}</Button>
          </div>
        }
      />

      <div className="u-stack-16">
        <div className="u-wrap-8">
          <StatusBadge caps={false}>{etiquetaAmbito(t, table.applies_to)}</StatusBadge>
          {table.is_default && <StatusBadge kind="accent" caps={false}>{t('tarifas_ui.por_defecto')}</StatusBadge>}
          {avgMargin !== null && <StatusBadge kind="success" caps={false}>{t('tarifas_ui.margen_medio', { n: avgMargin })}</StatusBadge>}
        </div>

        {entries.length === 0 ? (
          <EmptyState icon={<Coins size={28} />} title={t('ratecards.sin_tarifas')} description={t('tarifas_ui.sin_tarifas_desc')}
            ctaLabel={t('ratecards.nueva_tarifa')} onCta={() => setShowEntry(true)} />
        ) : (
          <Card className="rc-tabla-card">
            <div className="rc-tabla-scroll">
            <TablaSimple claseTabla="rc-tabla">
              <thead>
                <tr>
                  {[t('tarifas_ui.rol_perfil'), t('tarifas_ui.col_facturacion'), t('tarifas_ui.col_coste'), t('tarifas_ui.col_margen'), t('tarifas_ui.col_escalado'), t('tarifas_ui.col_vigencia'), ''].map((h, i) => (
                    <th className="rc-th" key={i}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {entries.map(e => {
                  const margin = e.billing_rate && e.cost_rate
                    ? Math.round((1 - Number(e.cost_rate) / Number(e.billing_rate)) * 100) : null
                  return (
                    <tr className="rc-tr" key={e.id}>
                      <td className="rc-td rc-td--nombre">{e.label}</td>
                      <td className="rc-td rc-td--cifra rc-td--fuerte">
                        {e.billing_rate ? `${fmtMoneda(e.billing_rate)}/h` : '—'}
                      </td>
                      <td className="rc-td rc-td--cifra rc-td--suave">
                        {e.cost_rate ? `${fmtMoneda(e.cost_rate)}/h` : '—'}
                      </td>
                      <td className="rc-td">
                        {margin !== null && (
                          <span className="rc-margen" style={{ '--rc-color': margin > 50 ? 'var(--success)' : margin > 30 ? 'var(--warning)' : 'var(--danger)' } as CSSProperties}>
                            {margin}%
                          </span>
                        )}
                      </td>
                      <td className="rc-td rc-td--suave">
                        {(e.escalation_pct ?? 0) > 0 ? t('tarifas_ui.pct_anio', { n: e.escalation_pct ?? 0 }) : '—'}
                      </td>
                      <td className="rc-td rc-td--suave">{vigencia(e)}</td>
                      <td className="rc-td">
                        <div className="u-row-center-6">
                          <Pulsable className="rc-icono" aria-label={t('common.edit')} title={t('common.edit')} onClick={() => setEditEntry(e)}><Pencil size={14} aria-hidden /></Pulsable>
                          <Pulsable className="rc-icono rc-icono--borrar" aria-label={t('common.delete')} title={t('common.delete')} onClick={() => { openConfirmGlobal({ message: t('tarifas_ui.eliminar_tarifa_confirm', { nombre: e.label }), onConfirm: () => deleteEntry(e.id), danger: true }) }}><Trash2 size={14} aria-hidden /></Pulsable>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </TablaSimple>
            </div>
          </Card>
        )}
      </div>

      {(showEntry || editEntry) && (
        <EntryForm tableId={tableId} entry={editEntry} onClose={() => { setShowEntry(false); setEditEntry(null) }} />
      )}

      {showDupe && (
        <Modal open title={t('ratecards.duplicar_tabla_con_escalado')} onClose={() => setShowDupe(false)} width={420}>
          <div className="u-stack-16">
            <Input label={t('tarifas_ui.escalado_anual_pct')} type="number" value={dupeEsc} onChange={e => setDupeEsc(+e.target.value)}
              hint={t('ratecards.copia_con_incremento', { nombre: table.name })} />
            <div className="rc-acciones">
              <Button variant="secondary" onClick={() => setShowDupe(false)}>{t('common.cancel')}</Button>
              <Button icon={<Copy size={14} />} onClick={() => duplicate()} loading={duping}>{t('tarifas_ui.duplicar_pct', { n: dupeEsc })}</Button>
            </div>
          </div>
        </Modal>
      )}
    </PageShell>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
export default function RateCardsPage() {
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

  const abrirConTeclado = (e: KeyboardEvent, id: string | number) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(id) }
  }

  return (
    <PageShell>
      <PageHeader icon={<Tag size={18} />} title={t('nav.rate_cards')} subtitle={t('rate_cards.subtitle')}
        actions={<Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('ratecards.nueva_tabla_de_tarifas')}</Button>} />

      {isLoading ? (
        <div className="rc-cargando"><Spinner /></div>
      ) : tables.length === 0 ? (
        <EmptyState icon={<Table2 size={28} />} title={t('ratecards.sin_tablas_de_tarifas')} description={t('tarifas_ui.sin_tablas_desc')}
          ctaLabel={t('ratecards.nueva_tabla_de_tarifas')} onCta={() => setShowCreate(true)} />
      ) : (
        <div className="ds-grid-cards">
          {tables.map(tabla => (
            <div className={`ds-card rc-tarjeta${tabla.is_default ? ' rc-tarjeta--defecto' : ''}`} key={tabla.id}
              role="button" tabIndex={0}
              onClick={() => setSelected(tabla.id)}
              onKeyDown={e => abrirConTeclado(e, tabla.id)}
            >
              <div className="rc-tarjeta__cabecera">
                <div className="rc-tarjeta__nombre">{tabla.name}</div>
                <div className="u-wrap-6">
                  {tabla.is_default && <StatusBadge kind="accent" caps={false}>{t('tarifas_ui.por_defecto')}</StatusBadge>}
                  <StatusBadge caps={false}>{etiquetaAmbito(t, tabla.applies_to)}</StatusBadge>
                </div>
              </div>
              {tabla.description && <div className="rc-tarjeta__desc">{tabla.description}</div>}
              <div className="rc-tarjeta__pie">
                <span className="rc-tarjeta__dato">
                  <Coins size={13} aria-hidden />
                  {tabla.entry_count === 1 ? t('tarifas_ui.una_tarifa') : t('tarifas_ui.n_tarifas', { n: tabla.entry_count || 0 })}
                </span>
                <Pulsable className="rc-icono rc-icono--borrar" aria-label={t('tarifas_ui.eliminar_tabla')} title={t('tarifas_ui.eliminar_tabla')} onClick={e => { e.stopPropagation(); openConfirmGlobal({message: t('tarifas_ui.eliminar_tabla_confirm', { nombre: tabla.name }), onConfirm: () => del(tabla.id),danger:true}) }}
                  onKeyDown={e => e.stopPropagation()}>
                  <Trash2 size={14} aria-hidden />
                </Pulsable>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <Modal open title={t('ratecards.nueva_tabla_de_tarifas_2')} onClose={() => setShowCreate(false)} width={480}>
          <div className="u-stack-14">
            <Input label={t('tarifas_ui.nombre_req')} value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} placeholder={t('ratecards.nombre_de_la_tabla')} />
            <Input label={t('ratecards.descripcion')} value={form.description} onChange={e => setForm(f=>({...f,description:e.target.value}))} placeholder={t('tarifas_ui.descripcion_opcional')} />
            <Select label={t('tarifas_ui.aplicar_a')} value={form.applies_to} onChange={e => setForm(f=>({...f,applies_to:e.target.value as AppliesTo}))} options={[
              { value: 'role', label: t('ratecards.por_rol_perfil') },
              { value: 'department', label: t('ratecards.por_departamento') },
              { value: 'client', label: t('ratecards.por_cliente') },
            ]} />
            <Checkbox className="rc-check" checked={!!form.is_default} onChange={v => setForm(f=>({...f,is_default:v}))} label={t('ratecards.tabla_por_defecto_se_usa_cuando_no')} />
            <div className="rc-acciones">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>{t('common.cancel')}</Button>
              <Button icon={<Plus size={14} />} onClick={createTable} loading={isPending} disabled={!form.name}>{t('tarifas_ui.crear_tabla')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </PageShell>
  )
}
