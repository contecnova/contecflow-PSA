import { useMemo, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Megaphone, Plus, Trash2, ExternalLink, FileText, Send, Briefcase, ChevronRight } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Badge, Button, Card, EmptyState, Input, Modal, Select, Spinner } from '../components/ui'
import { ClientSelect } from '../components/ui/EntitySelect'
import {
  useCreateOpportunity, useDeleteOpportunity, usePipeline, useUpdateOpportunity,
  useGenerateProposal, useMarkProposalSent, useConvertToProject,
} from '../hooks/usePipeline'
import { useToast } from '../context/ToastContext'
import { extractErr, fmtCurrency, fmtDate, fmtPct } from '../utils/helpers'
import { pipelineApi } from '../services/api'
import { openConfirmGlobal } from '../context/ConfirmContext'
import StatusBadge from '../components/ui/StatusBadge'

const STAGES = ['lead', 'qualification', 'proposal', 'negotiation', 'won', 'lost', 'cancelled']

type Opp = {
  [extra: string]: unknown
  id: string
  name?: string
  client_name?: string
  code?: string
  owner_id?: string
  owner_name?: string
  stage?: string
  proposal_status?: string
  proposal_generated_at?: string
  proposal_sent_at?: string
  project_id?: string
  contract_type?: string
  client_id?: string | null
  hourly_rate?: number | null
  expected_start_date?: string | null
  expected_duration_weeks?: number | null
  description?: string
  probability?: number
  expected_revenue?: number
  weighted_revenue?: number
  expected_close_date?: string
}

const STAGE_TRANSLATION_KEYS: Record<string, string> = {
  lead: 'pipeline.stage_lead',
  qualification: 'pipeline.stage_qualified',
  proposal: 'pipeline.stage_proposal',
  negotiation: 'pipeline.stage_negotiation',
  won: 'pipeline.stage_won',
  lost: 'pipeline.stage_lost',
  cancelled: 'common.cancel',
}

const STAGE_COLORS: Record<string, string> = {
  lead: 'var(--accent)',
  qualification: '#55c2ff',
  proposal: 'var(--warning)',
  negotiation: '#ff8b3d',
  won: 'var(--success)',
  lost: 'var(--danger)',
  cancelled: 'var(--text-3)',
}

const STAGE_TRANSITIONS: Record<string, string[]> = {
  lead: ['qualification', 'proposal', 'lost', 'cancelled'],
  qualification: ['lead', 'proposal', 'lost', 'cancelled'],
  proposal: ['qualification', 'negotiation', 'lost', 'cancelled'],
  negotiation: ['proposal', 'won', 'lost', 'cancelled'],
  won: [],
  lost: ['lead'],
  cancelled: [],
}

const PROPOSAL_STATUS_COLORS: Record<string, { bg: string; color: string; label: string }> = {
  none:      { bg: 'var(--surface-3)', color: 'var(--text-3)', label: 'Sin propuesta' },
  generated: { bg: 'var(--warning-bg)', color: 'var(--warning)', label: 'Propuesta generada' },
  sent:      { bg: 'var(--success-bg)', color: 'var(--success)', label: 'Propuesta enviada' },
}

const panelStyle: CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--surface-4)',
  borderRadius: 16,
}

const fieldLabelStyle: CSSProperties = {
  fontSize: "var(--text-xs)",
  fontWeight: 700,
  color: 'var(--text-2)',
  textTransform: 'uppercase',
  letterSpacing: '0.07em',
  marginBottom: 6,
  display: 'block',
}

const fieldStyle: CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  background: 'var(--surface-3)',
  border: '1px solid var(--surface-4)',
  borderRadius: 10,
  padding: '10px 12px',
  color: 'var(--text-1)',
  fontSize: "var(--text-base)",
  fontFamily: 'inherit',
  outline: 'none',
}

type OppForm = {
  name: string; client_name: string; stage: string; probability: number | string;
  expected_revenue: number | string; expected_close_date: string; description: string
  // Revisión 2026-11: lo que la conversión lleva al proyecto (cliente, tarifa) y al contrato de ingresos (tipo).
  client_id: string; contract_type: string; hourly_rate: number | string
  expected_start_date: string; expected_duration_weeks: number | string
}
const TIPOS_DE_CONTRATO = ['time_material', 'fixed_price', 'retainer', 'hourly_bag'] as const
function emptyForm(): OppForm {
  return {
    name: '',
    client_name: '',
    stage: 'lead',
    probability: 50,
    expected_revenue: '',
    expected_close_date: '',
    description: '',
    client_id: '', contract_type: '', hourly_rate: '', expected_start_date: '', expected_duration_weeks: '',
  }
}
function formDe(o: Opp): OppForm {
  return {
    name: o.name || '', client_name: o.client_name || '', stage: o.stage || 'lead', probability: o.probability ?? 50,
    expected_revenue: o.expected_revenue ?? '', expected_close_date: o.expected_close_date || '', description: o.description || '',
    client_id: o.client_id || '', contract_type: o.contract_type || '', hourly_rate: o.hourly_rate ?? '',
    expected_start_date: o.expected_start_date || '', expected_duration_weeks: o.expected_duration_weeks ?? '',
  }
}
const numOrNull = (v: number | string) => (v === '' || v === null ? null : Number(v))
function cuerpoDe(f: OppForm) {
  return {
    name: f.name.trim(), client_name: f.client_name.trim(), probability: Number(f.probability) || 0,
    expected_revenue: numOrNull(f.expected_revenue), expected_close_date: f.expected_close_date || null,
    description: f.description.trim() || null, client_id: f.client_id || null, contract_type: f.contract_type || null,
    hourly_rate: numOrNull(f.hourly_rate), expected_start_date: f.expected_start_date || null,
    expected_duration_weeks: numOrNull(f.expected_duration_weeks),
  }
}

/** Los campos de una oportunidad: en el alta y al editarla. */
function CamposDeOportunidad({ form, setForm }: { form: OppForm; setForm: (f: (c: OppForm) => OppForm) => void }) {
  const t = useAppT()
  const campo = (k: keyof OppForm) => (event: { target: { value: string } }) => setForm(c => ({ ...c, [k]: event.target.value }))
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(220px, 100%), 1fr))', gap: 12 }}>
      <Input label={t('pipeline.opportunity_name')} value={form.name} onChange={campo('name')} required placeholder={undefined} hint={undefined} />
      <div>
        <label style={fieldLabelStyle}>{t('pipeline.cliente_existente')}</label>
        <ClientSelect value={form.client_id} placeholder={t('pipeline.cliente_nuevo')} style={fieldStyle}
          onChange={(id, cliente) => setForm(c => ({ ...c, client_id: id, client_name: cliente ? cliente.name : c.client_name }))} />
      </div>
      {!form.client_id && <Input label={t('pipeline.client_name')} value={form.client_name} onChange={campo('client_name')} required placeholder={undefined} hint={undefined} />}
      <Input label={t('pipeline.value')} type="number" value={form.expected_revenue} onChange={campo('expected_revenue')} placeholder={undefined} required={undefined} hint={undefined} />
      <Input label={t('pipeline.probability')} type="number" value={form.probability} onChange={campo('probability')} placeholder={undefined} required={undefined} hint={undefined} />
      <Select label={t('pipeline.tipo_de_contrato')} value={form.contract_type} onChange={campo('contract_type')}
        options={[{ value: '', label: '—' }, ...TIPOS_DE_CONTRATO.map(c => ({ value: c, label: t(`pipeline.contrato_${c}`) }))]} />
      <Input label={t('pipeline.tarifa_hora')} type="number" value={form.hourly_rate} onChange={campo('hourly_rate')} placeholder={undefined} required={undefined} hint={undefined} />
      <Input label={t('pipeline.inicio_previsto')} type="date" value={form.expected_start_date} onChange={campo('expected_start_date')} placeholder={undefined} required={undefined} hint={undefined} />
      <Input label={t('pipeline.duracion_semanas')} type="number" value={form.expected_duration_weeks} onChange={campo('expected_duration_weeks')} placeholder={undefined} required={undefined} hint={undefined} />
      <Input label={t('pipeline.expected_close')} type="date" value={form.expected_close_date} onChange={campo('expected_close_date')} placeholder={undefined} required={undefined} hint={undefined} />
    </div>
  )
}

function ProposalStatusBadge({ status }: { status: string }) {
  const cfg = PROPOSAL_STATUS_COLORS[status] || PROPOSAL_STATUS_COLORS.none
  return (
    <StatusBadge color={cfg.color} caps={false}>{cfg.label}</StatusBadge>
  )
}

function SummaryCard({ label, value, tone = 'var(--text-1)', subvalue }: { label: ReactNode; value: ReactNode; tone?: string; subvalue?: ReactNode }) {
  return (
    <Card style={{ minWidth: 180, padding: 18 }}>
      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>
        {label}
      </div>
      <div style={{ fontSize: "var(--text-3xl)", fontWeight: 800, color: tone, lineHeight: 1, marginBottom: subvalue ? 6 : 0 }}>
        {value}
      </div>
      {subvalue ? <div className="u-text3-sm">{subvalue}</div> : null}
    </Card>
  )
}

type ConvertResult = { project_code?: string; message?: string; rev_contract_id?: string }

function OpportunityDetailModal({ opp, onClose, stageLabels, onUpdate }: { opp: Opp; onClose: () => void; stageLabels: Record<string, string>; onUpdate: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const [convertResult, setConvertResult] = useState<ConvertResult | null>(null)
  const [showProposal, setShowProposal] = useState(false)
  const [edicion, setEdicion] = useState<OppForm | null>(null)
  const updateOpportunity = useUpdateOpportunity()

  async function guardarEdicion() {
    if (!edicion) return
    if (!edicion.name.trim() || !edicion.client_name.trim()) { toast.error('Nombre y cliente son obligatorios'); return }
    try {
      await updateOpportunity.mutateAsync({ id: opp.id, data: cuerpoDe(edicion) })
      toast.success('Oportunidad guardada')
      setEdicion(null)
      onUpdate()
    } catch (e) {
      toast.error(extractErr(e, 'No se pudo guardar la oportunidad'))
    }
  }

  const generateProposal = useGenerateProposal()
  const markProposalSent = useMarkProposalSent()
  const convertToProject = useConvertToProject()

  // Fetch proposal content on demand
  const { data: proposalData, refetch: refetchProposal, isFetching: fetchingProposal } = useQuery<{ proposal_content?: string }>({
    queryKey: ['pipeline-proposal', opp.id],
    queryFn: () => pipelineApi.getProposal(opp.id).then(r => r.data),
    enabled: false,
    staleTime: 0,
  })

  async function handleGenerateProposal() {
    try {
      await generateProposal.mutateAsync({ id: opp.id, payload: {} })
      toast.success('Propuesta generada correctamente')
      onUpdate()
    } catch (e) {
      toast.error(extractErr(e, 'No se pudo generar la propuesta'))
    }
  }

  async function handleMarkSent() {
    try {
      await markProposalSent.mutateAsync(opp.id)
      toast.success('Propuesta marcada como enviada al cliente')
      onUpdate()
    } catch (e) {
      toast.error(extractErr(e, 'Error al marcar como enviada'))
    }
  }

  function handleConvert() {
    openConfirmGlobal({
      message: `¿Convertir "${opp.name}" a proyecto? Se marcará la oportunidad como ganada y se creará un contrato ASC 606 automáticamente.`,
      onConfirm: async () => { await doConvert() },
      danger: true,
    })
  }

  async function doConvert() {
    try {
      const res = (await convertToProject.mutateAsync(opp.id)) as { data: ConvertResult }
      setConvertResult(res.data)
      toast.success(`Proyecto ${res.data.project_code} creado correctamente`)
      onUpdate()
    } catch (e) {
      toast.error(extractErr(e, 'No se pudo convertir la oportunidad'))
    }
  }

  async function handleViewProposal() {
    setShowProposal(true)
    await refetchProposal()
  }

  const proposalStatus = opp.proposal_status || 'none'
  const hasProposal = proposalStatus !== 'none'
  const alreadyConverted = !!opp.project_id

  return (
    <>
      <Modal open onClose={onClose} title={opp.name} width={680}>
        <div style={{ display: 'grid', gap: 20 }}>

          {edicion ? (
            <div style={{ display: 'grid', gap: 12 }}>
              <CamposDeOportunidad form={edicion} setForm={f => setEdicion(c => (c ? f(c) : c))} />
              <div>
                <label style={fieldLabelStyle}>{t('pipeline.descripcion')}</label>
                <textarea value={edicion.description} onChange={e => setEdicion(c => (c ? { ...c, description: e.target.value } : c))}
                  rows={3} style={{ ...fieldStyle, resize: 'vertical' }} />
              </div>
              <div className="u-actions-8">
                <Button variant="secondary" onClick={() => setEdicion(null)}>Cancelar</Button>
                <Button onClick={guardarEdicion} loading={updateOpportunity.isPending}>Guardar</Button>
              </div>
            </div>
          ) : !alreadyConverted && (
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Button size="sm" variant="secondary" onClick={() => setEdicion(formDe(opp))}>{t('pipeline.editar')}</Button>
            </div>
          )}

          {/* Info */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(160px, 100%), 1fr))', gap: 12, background: 'var(--surface-2)', borderRadius: 10, padding: 16 }}>
            {[
              { label: 'Cliente', value: opp.client_name || '—' },
              { label: 'Código', value: opp.code || '—' },
              { label: 'Responsable', value: opp.owner_name || '—' },
              { label: 'Valor esperado', value: fmtCurrency(opp.expected_revenue) },
              { label: 'Probabilidad', value: fmtPct(opp.probability) },
              { label: 'Ponderado', value: fmtCurrency(opp.weighted_revenue) },
              { label: 'Etapa', value: stageLabels[opp.stage || ''] || opp.stage },
              { label: 'Cierre estimado', value: fmtDate(opp.expected_close_date) },
              { label: 'Tipo contrato', value: opp.contract_type ? t(`pipeline.contrato_${opp.contract_type}`) : '—' },
              { label: 'Tarifa/h', value: opp.hourly_rate != null ? fmtCurrency(opp.hourly_rate) : '—' },
              { label: 'Inicio previsto', value: fmtDate(opp.expected_start_date || undefined) },
            ].map(({ label, value }) => (
              <div key={label}>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 3 }}>{label}</div>
                <div className="u-base-600">{value}</div>
              </div>
            ))}
          </div>

          {opp.description ? (
            <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', lineHeight: 1.5, background: 'var(--surface-2)', borderRadius: 10, padding: '12px 14px' }}>
              {opp.description}
            </div>
          ) : null}

          {/* Propuesta SOW */}
          <div style={{ border: '1px solid var(--surface-4)', borderRadius: 12, padding: 16, display: 'grid', gap: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
              <div className="u-row-center-10">
                <FileText size={16} style={{ color: 'var(--accent)' }} />
                <span className="u-md-700">Propuesta SOW</span>
              </div>
              <ProposalStatusBadge status={proposalStatus} />
            </div>

            {opp.proposal_generated_at ? (
              <div className="u-text3-sm">
                Generada: {opp.proposal_generated_at}
                {opp.proposal_sent_at ? ` · Enviada: ${opp.proposal_sent_at}` : ''}
              </div>
            ) : null}

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <Button
                onClick={handleGenerateProposal}
                loading={generateProposal.isPending}
                variant={hasProposal ? 'secondary' : 'primary'}
                icon={<FileText size={13} />}
              >
                {hasProposal ? 'Regenerar propuesta' : 'Generar propuesta'}
              </Button>

              {hasProposal && (
                <Button
                  onClick={handleViewProposal}
                  variant="secondary"
                  loading={fetchingProposal}
                  icon={<ExternalLink size={13} />}
                >
                  Ver propuesta
                </Button>
              )}

              {proposalStatus === 'generated' && (
                <Button
                  onClick={handleMarkSent}
                  loading={markProposalSent.isPending}
                  icon={<Send size={13} />}
                >
                  {t('pipeline.marcar_como_enviada_al_cliente')}
                </Button>
              )}
            </div>
          </div>

          {/* Conversión a proyecto */}
          <div style={{ border: '1px solid var(--surface-4)', borderRadius: 12, padding: 16, display: 'grid', gap: 14 }}>
            <div className="u-row-center-10">
              <Briefcase size={16} style={{ color: 'var(--success)' }} />
              <span className="u-md-700">{t('pipeline.conversion_a_proyecto')}</span>
            </div>

            {alreadyConverted ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: "var(--text-base)", color: 'var(--success)', background: 'var(--success-bg)', borderRadius: 8, padding: '8px 12px' }}>
                <Briefcase size={14} />
                {t('pipeline.vinculada_al_proyecto')} <strong style={{ marginLeft: 4 }}>{opp.project_id}</strong>
              </div>
            ) : convertResult ? (
              <div style={{ fontSize: "var(--text-base)", color: 'var(--success)', background: 'var(--success-bg)', borderRadius: 8, padding: '10px 14px' }}>
                <div style={{ fontWeight: 700, marginBottom: 4 }}>Proyecto creado: {convertResult.project_code}</div>
                <div className="u-text2">{convertResult.message}</div>
                {convertResult.rev_contract_id && (
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--accent)', marginTop: 4 }}>{t('pipeline.contrato_asc_606_creado_automaticamente')}</div>
                )}
              </div>
            ) : ['lost', 'cancelled'].includes(String(opp.stage)) ? (
              // Una oportunidad perdida o cancelada no se convierte (revisión 2026-11).
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.5 }}>
                {t('pipeline.no_se_convierte_perdida')}
              </div>
            ) : (
              <>
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.5 }}>
                  {t('pipeline.convierte_esta_oportunidad_en_un_proyecto_activo')}
                </div>
                <div>
                  <Button
                    onClick={handleConvert}
                    loading={convertToProject.isPending}
                    icon={<ChevronRight size={13} />}
                  >
                    Convertir a proyecto
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      </Modal>

      {/* Proposal preview modal */}
      {showProposal && (
        <Modal open onClose={() => setShowProposal(false)} title="Propuesta SOW" width={780}>
          {fetchingProposal ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}><Spinner size={28} /></div>
          ) : (
            <pre style={{
              whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'var(--font-mono)',
              fontSize: "var(--text-sm)", lineHeight: 1.7, color: 'var(--text-1)',
              background: 'var(--surface-2)', borderRadius: 8, padding: '16px 18px',
              maxHeight: '60vh', overflowY: 'auto', margin: 0,
            }}>
              {proposalData?.proposal_content || '(sin contenido)'}
            </pre>
          )}
        </Modal>
      )}
    </>
  )
}

export default function PipelinePage() {
  const t = useAppT()
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [ownerFilter, setOwnerFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState(() => emptyForm())
  const [detailOpp, setDetailOpp] = useState<Opp | null>(null)

  const { data: rawData, isLoading, isError, error, refetch, isFetching } = usePipeline()
  // useMemo (auditoría 2026-08, P1-6): con `?? []` / `|| []` esto creaba un
  // array nuevo en cada render, así que los useMemo/useEffect que lo tienen
  // como dependencia se reejecutaban SIEMPRE — no memoizaban nada.
  const data: Opp[] = useMemo(() => (Array.isArray(rawData) ? (rawData as Opp[]) : []), [rawData])
  const createOpportunity = useCreateOpportunity()
  const updateOpportunity = useUpdateOpportunity()
  const deleteOpportunity = useDeleteOpportunity()

  const stageLabels = useMemo<Record<string, string>>(() => ({
    lead: t(STAGE_TRANSLATION_KEYS.lead),
    qualification: t(STAGE_TRANSLATION_KEYS.qualification),
    proposal: t(STAGE_TRANSLATION_KEYS.proposal),
    negotiation: t(STAGE_TRANSLATION_KEYS.negotiation),
    won: t(STAGE_TRANSLATION_KEYS.won),
    lost: t(STAGE_TRANSLATION_KEYS.lost),
    cancelled: 'Cancelada',
  }), [t])

  const owners = useMemo(() => {
    const seen = new Map<string, string>()
    data.forEach((opportunity) => {
      if (opportunity.owner_id && !seen.has(opportunity.owner_id)) {
        seen.set(opportunity.owner_id, opportunity.owner_name || 'Sin asignar')
      }
    })
    return Array.from(seen.entries()).map(([value, label]) => ({ value, label }))
  }, [data])

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return data.filter((opportunity) => {
      if (ownerFilter && opportunity.owner_id !== ownerFilter) return false
      if (!needle) return true
      return [
        opportunity.name,
        opportunity.client_name,
        opportunity.code,
        opportunity.owner_name,
      ].filter(Boolean).some((value) => String(value).toLowerCase().includes(needle))
    })
  }, [data, ownerFilter, search])

  const grouped = useMemo(() => {
    const buckets: Record<string, Opp[]> = Object.fromEntries(STAGES.map((stage) => [stage, [] as Opp[]]))
    filtered.forEach((opportunity) => {
      const stage = opportunity.stage && STAGES.includes(opportunity.stage) ? opportunity.stage : 'lead'
      buckets[stage].push(opportunity)
    })
    return buckets
  }, [filtered])

  const summary = useMemo(() => {
    const open = filtered.filter((item) => !['won', 'lost', 'cancelled'].includes(item.stage || ''))
    const closed = filtered.filter((item) => ['won', 'lost'].includes(item.stage || ''))
    const won = filtered.filter((item) => item.stage === 'won')
    return {
      totalRevenue: filtered.reduce((acc, item) => acc + (item.expected_revenue || 0), 0),
      weightedRevenue: filtered.reduce((acc, item) => acc + (item.weighted_revenue || 0), 0),
      openCount: open.length,
      winRate: closed.length ? (won.length / closed.length) * 100 : 0,
    }
  }, [filtered])

  // Keep detailOpp in sync with fresh list data
  const detailOppFresh = detailOpp
    ? (data.find(o => o.id === detailOpp.id) || detailOpp)
    : null

  async function handleCreate(event: { preventDefault: () => void }) {
    event.preventDefault()
    if (!form.name.trim() || !form.client_name.trim()) {
      toast.error('Nombre y cliente son obligatorios')
      return
    }

    try {
      await createOpportunity.mutateAsync({ ...cuerpoDe(form), stage: form.stage })
      toast.success('Oportunidad creada')
      setForm(emptyForm())
      setShowCreate(false)
    } catch (mutationError) {
      toast.error(extractErr(mutationError, 'No se pudo crear la oportunidad'))
    }
  }

  async function handleStageChange(opportunity: Opp, nextStage: string, selectElement: HTMLSelectElement | null) {
    if (!nextStage || nextStage === opportunity.stage) return
    try {
      await updateOpportunity.mutateAsync({ id: opportunity.id, data: { stage: nextStage } })
      toast.success(`Etapa actualizada a ${stageLabels[nextStage] || nextStage}`)
    } catch (mutationError) {
      if (selectElement) selectElement.value = opportunity.stage || ''
      toast.error(extractErr(mutationError, 'No se pudo actualizar la etapa'))
    }
  }

  function handleDelete(opportunity: Opp) {
    openConfirmGlobal({
      message: `¿Eliminar la oportunidad "${opportunity.name}"? Esta acción no se puede deshacer.`,
      danger: true,
      onConfirm: async () => {
        try {
          await deleteOpportunity.mutateAsync(opportunity.id)
          toast.success('Oportunidad eliminada')
        } catch (mutationError) {
          toast.error(extractErr(mutationError, 'No se pudo eliminar la oportunidad'))
        }
      },
    })
  }

  return (
    <PageShell style={{ display: 'grid', gap: 18 }}>
      <PageHeader
        icon={<Megaphone size={18} />}
        title={t('pipeline.title')}
        subtitle={t('pipeline.subtitle')}
        showListExport={filtered.length > 0}
        exportTargetSelector='[data-export-table="pipeline-list"]'
        exportFilePrefix='pipeline'
      />

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <SummaryCard label={t('pipeline.total_pipeline')} value={fmtCurrency(summary.totalRevenue)} tone="var(--accent)" />
        <SummaryCard label={t('pipeline.weighted_value')} value={fmtCurrency(summary.weightedRevenue)} tone="var(--warning)" />
        <SummaryCard label="Oportunidades abiertas" value={summary.openCount} subvalue={`${filtered.length} totales`} />
        <SummaryCard label="Win rate" value={fmtPct(summary.winRate)} tone="var(--success)" />
      </div>

      <div style={{ ...panelStyle, padding: 16, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'end' }}>
        <Input
          label="Buscar"
          value={search}
          onChange={(event: { target: { value: string } }) => setSearch(event.target.value)}
          placeholder={t('pipeline.nombre_cliente_codigo_o_responsable')}
          style={{ flex: '1 1 260px' }}
          required={undefined}
          hint={undefined}
        />
        <Select
          label="Responsable"
          value={ownerFilter}
          onChange={(event: { target: { value: string } }) => setOwnerFilter(event.target.value)}
          options={owners}
          style={{ width: 240 }}
        />
        <Button variant="secondary" onClick={() => { setSearch(''); setOwnerFilter('') }}>
          Limpiar
        </Button>
        <Button onClick={() => setShowCreate(true)} icon={<Plus size={14} />}>
          {t('pipeline.new_opportunity')}
        </Button>
      </div>

      {isLoading ? (
        <div style={{ ...panelStyle, padding: 24, display: 'flex', justifyContent: 'center' }}>
          <Spinner size={28} />
        </div>
      ) : null}

      {isError ? (
        <div style={{ ...panelStyle, padding: 20, color: 'var(--danger)' }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>{t('pipeline.no_se_pudo_cargar_el_pipeline')}</div>
          <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginBottom: 14 }}>{extractErr(error, 'Error inesperado')}</div>
          <Button onClick={() => refetch()} loading={isFetching}>Reintentar</Button>
        </div>
      ) : null}

      {!isLoading && !isError && filtered.length === 0 ? (
        <div style={{ ...panelStyle, padding: 28 }}>
          <EmptyState
            icon="chart"
            title={t('pipeline.no_hay_oportunidades_visibles')}
            description={data.length === 0 ? 'Crea la primera oportunidad para empezar a usar el pipeline comercial.' : 'Ajusta los filtros o crea una nueva oportunidad.'}
            ctaLabel={t('pipeline.new_opportunity')}
            onCta={() => setShowCreate(true)}
          />
        </div>
      ) : null}

      {!isLoading && !isError && filtered.length > 0 ? (
        <div data-export-table="pipeline-list" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 14, alignItems: 'start' }}>
          {STAGES.map((stage) => {
            const opportunities = grouped[stage] || []
            const totalStageRevenue = opportunities.reduce((acc, item) => acc + (item.expected_revenue || 0), 0)
            return (
              <section key={stage} style={{ ...panelStyle, padding: 14, minHeight: 180 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14, gap: 12 }}>
                  <div>
                    <div style={{ fontSize: "var(--text-sm)", color: STAGE_COLORS[stage], fontWeight: 800, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                      {stageLabels[stage] || stage}
                    </div>
                    <div className="u-hint">
                      {opportunities.length} oportunidad(es) · {fmtCurrency(totalStageRevenue)}
                    </div>
                  </div>
                  <Badge label={stage} display={opportunities.length} _color={undefined} />
                </div>

                <div style={{ display: 'grid', gap: 10 }}>
                  {opportunities.length === 0 ? (
                    <div style={{ border: '1px dashed var(--surface-4)', borderRadius: 12, padding: 16, fontSize: "var(--text-sm)", color: 'var(--text-3)', textAlign: 'center' }}>
                      {t('pipeline.sin_oportunidades_en_esta_etapa')}
                    </div>
                  ) : opportunities.map((opportunity) => {
                    const allowedStages = [opportunity.stage, ...(STAGE_TRANSITIONS[opportunity.stage || ''] || [])]
                    const proposalStatus = opportunity.proposal_status || 'none'
                    const psCfg = PROPOSAL_STATUS_COLORS[proposalStatus]
                    return (
                      <Card key={opportunity.id} style={{ padding: 14, display: 'grid', gap: 10 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'start' }}>
                          <div className="u-flex1-min0">
                            <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{opportunity.name}</div>
                            <div className="u-text2-sm">{opportunity.client_name || 'Sin cliente'}</div>
                            <div className="u-hint">{opportunity.code || 'Sin código'}</div>
                          </div>
                          <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                            <button
                              type="button"
                              onClick={() => setDetailOpp(opportunity)}
                              title="Ver detalles y gestionar propuesta"
                              style={{ background: 'var(--accent-muted,rgba(0,212,255,0.08))', border: 'none', color: 'var(--accent)', cursor: 'pointer', padding: '4px 6px', borderRadius: 6 }}
                            >
                              <FileText size={14} />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDelete(opportunity)}
                              title="Eliminar oportunidad"
                              style={{ background: 'transparent', border: 'none', color: 'var(--danger)', cursor: 'pointer', padding: 2 }}
                            >
                              <Trash2 size={15} />
                            </button>
                          </div>
                        </div>

                        <div style={{ display: 'grid', gap: 6, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                            <span>Valor</span>
                            <strong className="u-text1">{fmtCurrency(opportunity.expected_revenue)}</strong>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                            <span>Probabilidad</span>
                            <strong className="u-text1">{fmtPct(opportunity.probability)}</strong>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                            <span>Ponderado</span>
                            <strong className="u-warning">{fmtCurrency(opportunity.weighted_revenue)}</strong>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                            <span>Cierre</span>
                            <strong className="u-text1">{fmtDate(opportunity.expected_close_date)}</strong>
                          </div>
                        </div>

                        {/* Proposal status indicator */}
                        {proposalStatus !== 'none' && (
                          <div style={{ fontSize: "var(--text-xs)", padding: '3px 8px', borderRadius: 6, background: psCfg.bg, color: psCfg.color, fontWeight: 600, width: 'fit-content' }}>
                            {psCfg.label}
                          </div>
                        )}

                        <div style={{ display: 'grid', gap: 8 }}>
                          <div className="u-text3-xs">
                            Responsable: {opportunity.owner_name || 'Sin asignar'}
                          </div>
                          <label style={{ display: 'grid', gap: 6 }}>
                            <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Mover a etapa</span>
                            <select
                              key={`${opportunity.id}:${opportunity.stage}`}
                              defaultValue={opportunity.stage}
                              onChange={(event) => handleStageChange(opportunity, event.target.value, event.target)}
                              style={fieldStyle}
                              disabled={updateOpportunity.isPending}
                            >
                              {allowedStages.map((allowedStage) => (
                                <option key={allowedStage || ''} value={allowedStage || ''}>
                                  {stageLabels[allowedStage || ''] || allowedStage}
                                </option>
                              ))}
                            </select>
                          </label>
                        </div>

                        {opportunity.description ? (
                          <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', lineHeight: 1.45, borderTop: '1px solid var(--surface-4)', paddingTop: 10 }}>
                            {opportunity.description}
                          </div>
                        ) : null}
                      </Card>
                    )
                  })}
                </div>
              </section>
            )
          })}
        </div>
      ) : null}

      {/* Create modal */}
      <Modal open={showCreate} onClose={() => setShowCreate(false)} title={t('pipeline.new_opportunity')} width={620}>
        <form onSubmit={handleCreate} style={{ display: 'grid', gap: 16 }}>
          <CamposDeOportunidad form={form} setForm={setForm} />
          <Select
            label={t('pipeline.stage')}
            value={form.stage}
            onChange={(event: { target: { value: string } }) => setForm((current) => ({ ...current, stage: event.target.value }))}
            options={STAGES.map((stage) => ({ value: stage, label: stageLabels[stage] || stage }))}
          />

          <div>
            <label style={fieldLabelStyle}>{t('pipeline.descripcion')}</label>
            <textarea
              value={form.description}
              onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
              rows={4}
              style={{ ...fieldStyle, resize: 'vertical' }}
            />
          </div>

          <div className="u-actions-10">
            <Button variant="secondary" onClick={() => setShowCreate(false)}>
              Cancelar
            </Button>
            <Button type="submit" loading={createOpportunity.isPending}>
              Crear oportunidad
            </Button>
          </div>
        </form>
      </Modal>

      {/* Detail + proposal + convert modal */}
      {detailOppFresh && (
        <OpportunityDetailModal
          opp={detailOppFresh}
          stageLabels={stageLabels}
          onClose={() => setDetailOpp(null)}
          onUpdate={() => {}}
        />
      )}
    </PageShell>
  )
}
