import { useMemo, useState, useId } from 'react'
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
import type { Oportunidad, OportunidadConvertida, Propuesta } from '../services/api/tipos-personas'
import { openConfirmGlobal } from '../context/ConfirmContext'
import StatusBadge from '../components/ui/StatusBadge'
import { STALE_ALWAYS } from '../constants/timings'
import './PipelinePage.css'

const STAGES = ['lead', 'qualification', 'proposal', 'negotiation', 'won', 'lost', 'cancelled']

/** `serialize_opportunity` (app/services/pipeline_service.py). */
type Opp = Oportunidad

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
  none:      { bg: 'var(--surface-3)', color: 'var(--text-3)', label: 'pagina_pipe.sin_propuesta' },
  generated: { bg: 'var(--warning-bg)', color: 'var(--warning)', label: 'pagina_pipe.propuesta_generada' },
  sent:      { bg: 'var(--success-bg)', color: 'var(--success)', label: 'pagina_pipe.propuesta_enviada' },
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
  borderRadius: 'var(--radius-md)',
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
    <div className="pipe-grid">
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
  const t = useAppT()
  const cfg = PROPOSAL_STATUS_COLORS[status] || PROPOSAL_STATUS_COLORS.none
  return (
    <StatusBadge color={cfg.color} caps={false}>{t(cfg.label)}</StatusBadge>
  )
}

function SummaryCard({ label, value, tone = 'var(--text-1)', subvalue }: { label: ReactNode; value: ReactNode; tone?: string; subvalue?: ReactNode }) {
  return (
    <Card style={{ minWidth: 180, padding: 18 }}>
      <div className="pipe-box">
        {label}
      </div>
      <div className="pipe-box-2" style={{ color: tone, marginBottom: subvalue ? 6 : 0 }}>
        {value}
      </div>
      {subvalue ? <div className="u-text3-sm">{subvalue}</div> : null}
    </Card>
  )
}


function OpportunityDetailModal({ opp, onClose, stageLabels, onUpdate }: { opp: Opp; onClose: () => void; stageLabels: Record<string, string>; onUpdate: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const [convertResult, setConvertResult] = useState<OportunidadConvertida | null>(null)
  const [showProposal, setShowProposal] = useState(false)
  const [edicion, setEdicion] = useState<OppForm | null>(null)
  const updateOpportunity = useUpdateOpportunity()

  async function guardarEdicion() {
    if (!edicion) return
    if (!edicion.name.trim() || !edicion.client_name.trim()) { toast.error(t('pagina_pipe.nombre_y_cliente_son_obligatorios')); return }
    try {
      await updateOpportunity.mutateAsync({ id: opp.id, data: cuerpoDe(edicion) })
      toast.success(t('pagina_pipe.oportunidad_guardada'))
      setEdicion(null)
      onUpdate()
    } catch (e) {
      toast.error(extractErr(e, t('pagina_pipe.no_se_pudo_guardar_la_oportunidad')))
    }
  }

  const generateProposal = useGenerateProposal()
  const markProposalSent = useMarkProposalSent()
  const convertToProject = useConvertToProject()

  // Fetch proposal content on demand
  const { data: proposalData, refetch: refetchProposal, isFetching: fetchingProposal } = useQuery<Propuesta>({
    queryKey: ['pipeline-proposal', opp.id],
    queryFn: () => pipelineApi.getProposal(opp.id).then(r => r.data),
    enabled: false,
    staleTime: STALE_ALWAYS,
  })

  async function handleGenerateProposal() {
    try {
      await generateProposal.mutateAsync({ id: opp.id, payload: {} })
      toast.success(t('pagina_pipe.propuesta_generada_correctamente'))
      onUpdate()
    } catch (e) {
      toast.error(extractErr(e, t('pagina_pipe.no_se_pudo_generar_la_propuesta')))
    }
  }

  async function handleMarkSent() {
    try {
      await markProposalSent.mutateAsync(opp.id)
      toast.success(t('pagina_pipe.propuesta_marcada_como_enviada_al_cliente'))
      onUpdate()
    } catch (e) {
      toast.error(extractErr(e, t('pagina_pipe.error_al_marcar_como_enviada')))
    }
  }

  function handleConvert() {
    openConfirmGlobal({
      message: t('pagina_pipe.convertir_a_proyecto_se_marcara_la', { name: opp.name }),
      onConfirm: async () => { await doConvert() },
      danger: true,
    })
  }

  async function doConvert() {
    try {
      const res = await convertToProject.mutateAsync(opp.id)
      setConvertResult(res.data)
      toast.success(t('pagina_pipe.proyecto_creado_correctamente', { project_code: res.data.project_code }))
      onUpdate()
    } catch (e) {
      toast.error(extractErr(e, t('pagina_pipe.no_se_pudo_convertir_la_oportunidad')))
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
        <div className="pipe-grid-2">

          {edicion ? (
            <div className="pipe-grid-3">
              <CamposDeOportunidad form={edicion} setForm={f => setEdicion(c => (c ? f(c) : c))} />
              <div>
                <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={fieldLabelStyle}>{t('pipeline.descripcion')}</label>
                <textarea id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={edicion.description} onChange={e => setEdicion(c => (c ? { ...c, description: e.target.value } : c))}
                  rows={3} style={{ ...fieldStyle, resize: 'vertical' }} />
              </div>
              <div className="u-actions-8">
                <Button variant="secondary" onClick={() => setEdicion(null)}>{t('pagina_pipe.cancelar')}</Button>
                <Button onClick={guardarEdicion} loading={updateOpportunity.isPending}>{t('pagina_pipe.guardar')}</Button>
              </div>
            </div>
          ) : !alreadyConverted && (
            <div className="u-row-end">
              <Button size="sm" variant="secondary" onClick={() => setEdicion(formDe(opp))}>{t('pipeline.editar')}</Button>
            </div>
          )}

          {/* Info */}
          <div className="pipe-grid-4">
            {[
              { label: t('pagina_pipe.cliente'), value: opp.client_name || '—' },
              { label: t('pagina_pipe.codigo'), value: opp.code || '—' },
              { label: t('pagina_pipe.responsable'), value: opp.owner_name || '—' },
              { label: t('pagina_pipe.valor_esperado'), value: fmtCurrency(opp.expected_revenue) },
              { label: t('pagina_pipe.probabilidad'), value: fmtPct(opp.probability) },
              { label: t('pagina_pipe.ponderado'), value: fmtCurrency(opp.weighted_revenue) },
              { label: t('pagina_pipe.etapa'), value: stageLabels[opp.stage || ''] || opp.stage },
              { label: t('pagina_pipe.cierre_estimado'), value: fmtDate(opp.expected_close_date) },
              { label: t('pagina_pipe.tipo_contrato'), value: opp.contract_type ? t(`pipeline.contrato_${opp.contract_type}`) : '—' },
              { label: t('pagina_pipe.tarifa_h'), value: opp.hourly_rate != null ? fmtCurrency(opp.hourly_rate) : '—' },
              { label: t('pagina_pipe.inicio_previsto'), value: fmtDate(opp.expected_start_date || undefined) },
            ].map(({ label, value }) => (
              <div key={label}>
                <div className="pipe-box-3">{label}</div>
                <div className="u-base-600">{value}</div>
              </div>
            ))}
          </div>

          {opp.description ? (
            <div className="pipe-card">
              {opp.description}
            </div>
          ) : null}

          {/* Propuesta SOW */}
          <div className="pipe-grid-5">
            <div className="pipe-row">
              <div className="u-row-center-10">
                <FileText size={16} style={{ color: 'var(--accent)' }} />
                <span className="u-md-700">{t('pagina_pipe.propuesta_sow')}</span>
              </div>
              <ProposalStatusBadge status={proposalStatus} />
            </div>

            {opp.proposal_generated_at ? (
              <div className="u-text3-sm">
                {t('pagina_pipe.generada')}{' '}{opp.proposal_generated_at}
                {opp.proposal_sent_at ? t('pagina_pipe.enviada', { proposal_sent_at: opp.proposal_sent_at }) : ''}
              </div>
            ) : null}

            <div className="u-wrap-10">
              <Button
                onClick={handleGenerateProposal}
                loading={generateProposal.isPending}
                variant={hasProposal ? 'secondary' : 'primary'}
                icon={<FileText size={13} />}
              >
                {hasProposal ? t('pagina_pipe.regenerar_propuesta') : t('pagina_pipe.generar_propuesta')}
              </Button>

              {hasProposal && (
                <Button
                  onClick={handleViewProposal}
                  variant="secondary"
                  loading={fetchingProposal}
                  icon={<ExternalLink size={13} />}
                >
                  {t('pagina_pipe.ver_propuesta')}
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
          <div className="pipe-grid-5">
            <div className="u-row-center-10">
              <Briefcase size={16} style={{ color: 'var(--success)' }} />
              <span className="u-md-700">{t('pipeline.conversion_a_proyecto')}</span>
            </div>

            {alreadyConverted ? (
              <div className="pipe-row-2">
                <Briefcase size={14} />
                {t('pipeline.vinculada_al_proyecto')} <strong className="pipe-box-4">{opp.project_id}</strong>
              </div>
            ) : convertResult ? (
              <div className="pipe-card-2">
                <div className="pipe-box-5">{t('pagina_pipe.proyecto_creado')}{' '}{convertResult.project_code}</div>
                <div className="u-text2">{convertResult.message}</div>
                {convertResult.rev_contract_id && (
                  <div className="pipe-box-6">{t('pipeline.contrato_asc_606_creado_automaticamente')}</div>
                )}
              </div>
            ) : ['lost', 'cancelled'].includes(String(opp.stage)) ? (
              // Una oportunidad perdida o cancelada no se convierte (revisión 2026-11).
              <div className="pipe-box-7">
                {t('pipeline.no_se_convierte_perdida')}
              </div>
            ) : (
              <>
                <div className="pipe-box-7">
                  {t('pipeline.convierte_esta_oportunidad_en_un_proyecto_activo')}
                </div>
                <div>
                  <Button
                    onClick={handleConvert}
                    loading={convertToProject.isPending}
                    icon={<ChevronRight size={13} />}
                  >
                    {t('pagina_pipe.convertir_a_proyecto')}
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      </Modal>

      {/* Proposal preview modal */}
      {showProposal && (
        <Modal open onClose={() => setShowProposal(false)} title={t('pagina_pipe.propuesta_sow')} width={780}>
          {fetchingProposal ? (
            <div className="pipe-row-3"><Spinner size={28} /></div>
          ) : (
            <pre className="pipe-card-3">
              {proposalData?.proposal_content || t('pagina_pipe.sin_contenido')}
            </pre>
          )}
        </Modal>
      )}
    </>
  )
}

export default function PipelinePage() {
  const idCampo = useId()
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
  const data: Opp[] = useMemo(() => rawData ?? [], [rawData])
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
    cancelled: t('pagina_pipe.cancelada'),
  }), [t])

  const owners = useMemo(() => {
    const seen = new Map<string, string>()
    data.forEach((opportunity) => {
      if (opportunity.owner_id && !seen.has(opportunity.owner_id)) {
        seen.set(opportunity.owner_id, opportunity.owner_name || t('pagina_pipe.sin_asignar'))
      }
    })
    return Array.from(seen.entries()).map(([value, label]) => ({ value, label }))
  }, [data, t])

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
      toast.error(t('pagina_pipe.nombre_y_cliente_son_obligatorios'))
      return
    }

    try {
      await createOpportunity.mutateAsync({ ...cuerpoDe(form), stage: form.stage })
      toast.success(t('pagina_pipe.oportunidad_creada'))
      setForm(emptyForm())
      setShowCreate(false)
    } catch (mutationError) {
      toast.error(extractErr(mutationError, t('pagina_pipe.no_se_pudo_crear_la_oportunidad')))
    }
  }

  async function handleStageChange(opportunity: Opp, nextStage: string, selectElement: HTMLSelectElement | null) {
    if (!nextStage || nextStage === opportunity.stage) return
    try {
      await updateOpportunity.mutateAsync({ id: opportunity.id, data: { stage: nextStage } })
      toast.success(t('pagina_pipe.etapa_actualizada_a', { v1: stageLabels[nextStage] || nextStage }))
    } catch (mutationError) {
      if (selectElement) selectElement.value = opportunity.stage || ''
      toast.error(extractErr(mutationError, t('pagina_pipe.no_se_pudo_actualizar_la_etapa')))
    }
  }

  function handleDelete(opportunity: Opp) {
    openConfirmGlobal({
      message: t('pagina_pipe.eliminar_la_oportunidad_esta_accion_no', { name: opportunity.name }),
      danger: true,
      onConfirm: async () => {
        try {
          await deleteOpportunity.mutateAsync(opportunity.id)
          toast.success(t('pagina_pipe.oportunidad_eliminada'))
        } catch (mutationError) {
          toast.error(extractErr(mutationError, t('pagina_pipe.no_se_pudo_eliminar_la_oportunidad')))
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

      <div className="pipe-row-4">
        <SummaryCard label={t('pipeline.total_pipeline')} value={fmtCurrency(summary.totalRevenue)} tone="var(--accent)" />
        <SummaryCard label={t('pipeline.weighted_value')} value={fmtCurrency(summary.weightedRevenue)} tone="var(--warning)" />
        <SummaryCard label={t('pagina_pipe.oportunidades_abiertas')} value={summary.openCount} subvalue={t('pagina_pipe.totales', { length: filtered.length })} />
        <SummaryCard label={t('pagina_pipe.win_rate')} value={fmtPct(summary.winRate)} tone="var(--success)" />
      </div>

      <div style={{ ...panelStyle, padding: 16, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'end' }}>
        <Input
          label={t('pagina_pipe.buscar')}
          value={search}
          onChange={(event: { target: { value: string } }) => setSearch(event.target.value)}
          placeholder={t('pipeline.nombre_cliente_codigo_o_responsable')}
          style={{ flex: '1 1 260px' }}
          required={undefined}
          hint={undefined}
        />
        <Select
          label={t('pagina_pipe.responsable')}
          value={ownerFilter}
          onChange={(event: { target: { value: string } }) => setOwnerFilter(event.target.value)}
          options={owners}
          style={{ width: 240 }}
        />
        <Button variant="secondary" onClick={() => { setSearch(''); setOwnerFilter('') }}>
          {t('pagina_pipe.limpiar')}
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
          <div className="pipe-box-8">{t('pipeline.no_se_pudo_cargar_el_pipeline')}</div>
          <div className="pipe-box-9">{extractErr(error, t('pagina_pipe.error_inesperado'))}</div>
          <Button onClick={() => refetch()} loading={isFetching}>{t('pagina_pipe.reintentar')}</Button>
        </div>
      ) : null}

      {!isLoading && !isError && filtered.length === 0 ? (
        <div style={{ ...panelStyle, padding: 28 }}>
          <EmptyState
            icon="chart"
            title={t('pipeline.no_hay_oportunidades_visibles')}
            description={data.length === 0 ? t('pagina_pipe.crea_la_primera_oportunidad_para_empezar') : t('pagina_pipe.ajusta_los_filtros_o_crea_una')}
            ctaLabel={t('pipeline.new_opportunity')}
            onCta={() => setShowCreate(true)}
          />
        </div>
      ) : null}

      {!isLoading && !isError && filtered.length > 0 ? (
        <div data-export-table="pipeline-list" className="pipe-grid-6">
          {STAGES.map((stage) => {
            const opportunities = grouped[stage] || []
            const totalStageRevenue = opportunities.reduce((acc, item) => acc + (item.expected_revenue || 0), 0)
            return (
              <section key={stage} style={{ ...panelStyle, padding: 14, minHeight: 180 }}>
                <div className="pipe-row-5">
                  <div>
                    <div className="pipe-box-10" style={{ color: STAGE_COLORS[stage] }}>
                      {stageLabels[stage] || stage}
                    </div>
                    <div className="u-hint">
                      {opportunities.length}{' '}{t('pagina_pipe.oportunidad_es')}{' '}{fmtCurrency(totalStageRevenue)}
                    </div>
                  </div>
                  <Badge label={stage} display={opportunities.length} _color={undefined} />
                </div>

                <div className="pipe-grid-7">
                  {opportunities.length === 0 ? (
                    <div className="pipe-card-4">
                      {t('pipeline.sin_oportunidades_en_esta_etapa')}
                    </div>
                  ) : opportunities.map((opportunity) => {
                    const allowedStages = [opportunity.stage, ...(STAGE_TRANSITIONS[opportunity.stage || ''] || [])]
                    const proposalStatus = opportunity.proposal_status || 'none'
                    const psCfg = PROPOSAL_STATUS_COLORS[proposalStatus]
                    return (
                      <Card key={opportunity.id} style={{ padding: 14, display: 'grid', gap: 10 }}>
                        <div className="pipe-row-6">
                          <div className="u-flex1-min0">
                            <div className="pipe-box-11">{opportunity.name}</div>
                            <div className="u-text2-sm">{opportunity.client_name || t('pagina_pipe.sin_cliente')}</div>
                            <div className="u-hint">{opportunity.code || t('pagina_pipe.sin_codigo')}</div>
                          </div>
                          <div className="pipe-row-7">
                            <button aria-label={t('pagina_pipe.ver_detalles_y_gestionar_propuesta')}
                              type="button"
                              onClick={() => setDetailOpp(opportunity)}
                              title={t('pagina_pipe.ver_detalles_y_gestionar_propuesta')}
                              className="pipe-btn"
                            >
                              <FileText size={14} />
                            </button>
                            <button aria-label={t('pagina_pipe.eliminar_oportunidad')}
                              type="button"
                              onClick={() => handleDelete(opportunity)}
                              title={t('pagina_pipe.eliminar_oportunidad')}
                              className="pipe-btn-2"
                            >
                              <Trash2 size={15} />
                            </button>
                          </div>
                        </div>

                        <div className="pipe-grid-8">
                          <div className="pipe-row-8">
                            <span>{t('pagina_pipe.valor')}</span>
                            <strong className="u-text1">{fmtCurrency(opportunity.expected_revenue)}</strong>
                          </div>
                          <div className="pipe-row-8">
                            <span>{t('pagina_pipe.probabilidad')}</span>
                            <strong className="u-text1">{fmtPct(opportunity.probability)}</strong>
                          </div>
                          <div className="pipe-row-8">
                            <span>{t('pagina_pipe.ponderado')}</span>
                            <strong className="u-warning">{fmtCurrency(opportunity.weighted_revenue)}</strong>
                          </div>
                          <div className="pipe-row-8">
                            <span>{t('pagina_pipe.cierre')}</span>
                            <strong className="u-text1">{fmtDate(opportunity.expected_close_date)}</strong>
                          </div>
                        </div>

                        {/* Proposal status indicator */}
                        {proposalStatus !== 'none' && (
                          <div className="pipe-box-12" style={{ background: psCfg.bg, color: psCfg.color }}>
                            {t(psCfg.label)}
                          </div>
                        )}

                        <div className="pipe-grid-9">
                          <div className="u-text3-xs">
                            {t('pagina_pipe.responsable_2')}{' '}{opportunity.owner_name || t('pagina_pipe.sin_asignar')}
                          </div>
                          <label className="pipe-label">
                            <span className="pipe-label-2">{t('pagina_pipe.mover_a_etapa')}</span>
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
                          <div className="pipe-box-13">
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
        <form onSubmit={handleCreate} className="pipe-grid-10">
          <CamposDeOportunidad form={form} setForm={setForm} />
          <Select
            label={t('pipeline.stage')}
            value={form.stage}
            onChange={(event: { target: { value: string } }) => setForm((current) => ({ ...current, stage: event.target.value }))}
            options={STAGES.map((stage) => ({ value: stage, label: stageLabels[stage] || stage }))}
          />

          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={fieldLabelStyle}>{t('pipeline.descripcion')}</label>
            <textarea id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`}
              value={form.description}
              onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
              rows={4}
              style={{ ...fieldStyle, resize: 'vertical' }}
            />
          </div>

          <div className="u-actions-10">
            <Button variant="secondary" onClick={() => setShowCreate(false)}>
              {t('pagina_pipe.cancelar')}
            </Button>
            <Button type="submit" loading={createOpportunity.isPending}>
              {t('pagina_pipe.crear_oportunidad')}
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
