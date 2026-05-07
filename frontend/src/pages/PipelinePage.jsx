import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Megaphone, Plus, Trash2, ExternalLink, FileText, Send, Briefcase, ChevronRight } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Badge, Button, Card, EmptyState, Input, Modal, Select, Spinner } from '../components/ui'
import {
  useCreateOpportunity, useDeleteOpportunity, usePipeline, useUpdateOpportunity,
  useGenerateProposal, useMarkProposalSent, useConvertToProject,
} from '../hooks/usePipeline'
import { useToast } from '../context/ToastContext'
import { extractErr, fmtCurrency, fmtDate, fmtPct } from '../utils/helpers'
import { pipelineApi } from '../services/api'

const STAGES = ['lead', 'qualification', 'proposal', 'negotiation', 'won', 'lost', 'cancelled']

const STAGE_TRANSLATION_KEYS = {
  lead: 'pipeline.stage_lead',
  qualification: 'pipeline.stage_qualified',
  proposal: 'pipeline.stage_proposal',
  negotiation: 'pipeline.stage_negotiation',
  won: 'pipeline.stage_won',
  lost: 'pipeline.stage_lost',
  cancelled: 'common.cancel',
}

const STAGE_COLORS = {
  lead: 'var(--accent)',
  qualification: '#55c2ff',
  proposal: 'var(--warning)',
  negotiation: '#ff8b3d',
  won: 'var(--success)',
  lost: 'var(--danger)',
  cancelled: 'var(--text-3)',
}

const STAGE_TRANSITIONS = {
  lead: ['qualification', 'proposal', 'lost', 'cancelled'],
  qualification: ['lead', 'proposal', 'lost', 'cancelled'],
  proposal: ['qualification', 'negotiation', 'lost', 'cancelled'],
  negotiation: ['proposal', 'won', 'lost', 'cancelled'],
  won: [],
  lost: ['lead'],
  cancelled: [],
}

const PROPOSAL_STATUS_COLORS = {
  none:      { bg: 'var(--surface-3)', color: 'var(--text-3)', label: 'Sin propuesta' },
  generated: { bg: 'var(--warning-bg)', color: 'var(--warning)', label: 'Propuesta generada' },
  sent:      { bg: 'var(--success-bg)', color: 'var(--success)', label: 'Propuesta enviada' },
}

const panelStyle = {
  background: 'var(--surface-2)',
  border: '1px solid var(--surface-4)',
  borderRadius: 16,
}

const fieldLabelStyle = {
  fontSize: "var(--text-xs)",
  fontWeight: 700,
  color: 'var(--text-2)',
  textTransform: 'uppercase',
  letterSpacing: '0.07em',
  marginBottom: 6,
  display: 'block',
}

const fieldStyle = {
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

function emptyForm() {
  return {
    name: '',
    client_name: '',
    stage: 'lead',
    probability: 50,
    expected_revenue: '',
    expected_close_date: '',
    description: '',
  }
}

function ProposalStatusBadge({ status }) {
  const cfg = PROPOSAL_STATUS_COLORS[status] || PROPOSAL_STATUS_COLORS.none
  return (
    <span style={{ fontSize: "var(--text-xs)", padding: '2px 8px', borderRadius: 6, background: cfg.bg, color: cfg.color, fontWeight: 600 }}>
      {cfg.label}
    </span>
  )
}

function SummaryCard({ label, value, tone = 'var(--text-1)', subvalue }) {
  return (
    <Card style={{ minWidth: 180, padding: 18 }}>
      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>
        {label}
      </div>
      <div style={{ fontSize: "var(--text-3xl)", fontWeight: 800, color: tone, lineHeight: 1, marginBottom: subvalue ? 6 : 0 }}>
        {value}
      </div>
      {subvalue ? <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>{subvalue}</div> : null}
    </Card>
  )
}

function OpportunityDetailModal({ opp, onClose, stageLabels, onUpdate }) {
  const toast = useToast()
  const [convertResult, setConvertResult] = useState(null)
  const [showProposal, setShowProposal] = useState(false)

  const generateProposal = useGenerateProposal()
  const markProposalSent = useMarkProposalSent()
  const convertToProject = useConvertToProject()

  // Fetch proposal content on demand
  const { data: proposalData, refetch: refetchProposal, isFetching: fetchingProposal } = useQuery({
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

  async function handleConvert() {
    if (!window.confirm(`¿Convertir "${opp.name}" a proyecto? Se marcará la oportunidad como ganada y se creará un contrato ASC 606 automáticamente.`)) return
    try {
      const res = await convertToProject.mutateAsync(opp.id)
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

          {/* Info */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, background: 'var(--surface-2)', borderRadius: 10, padding: 16 }}>
            {[
              { label: 'Cliente', value: opp.client_name || '—' },
              { label: 'Código', value: opp.code || '—' },
              { label: 'Responsable', value: opp.owner_name || '—' },
              { label: 'Valor esperado', value: fmtCurrency(opp.expected_revenue) },
              { label: 'Probabilidad', value: fmtPct(opp.probability) },
              { label: 'Ponderado', value: fmtCurrency(opp.weighted_revenue) },
              { label: 'Etapa', value: stageLabels[opp.stage] || opp.stage },
              { label: 'Cierre estimado', value: fmtDate(opp.expected_close_date) },
              { label: 'Tipo contrato', value: opp.contract_type || '—' },
            ].map(({ label, value }) => (
              <div key={label}>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 3 }}>{label}</div>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>{value}</div>
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
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <FileText size={16} style={{ color: 'var(--accent)' }} />
                <span style={{ fontWeight: 700, fontSize: "var(--text-md)" }}>Propuesta SOW</span>
              </div>
              <ProposalStatusBadge status={proposalStatus} />
            </div>

            {opp.proposal_generated_at ? (
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
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
                  Marcar como enviada al cliente
                </Button>
              )}
            </div>
          </div>

          {/* Conversión a proyecto */}
          <div style={{ border: '1px solid var(--surface-4)', borderRadius: 12, padding: 16, display: 'grid', gap: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Briefcase size={16} style={{ color: 'var(--success)' }} />
              <span style={{ fontWeight: 700, fontSize: "var(--text-md)" }}>Conversión a proyecto</span>
            </div>

            {alreadyConverted ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: "var(--text-base)", color: 'var(--success)', background: 'var(--success-bg)', borderRadius: 8, padding: '8px 12px' }}>
                <Briefcase size={14} />
                Vinculada al proyecto <strong style={{ marginLeft: 4 }}>{opp.project_id}</strong>
              </div>
            ) : convertResult ? (
              <div style={{ fontSize: "var(--text-base)", color: 'var(--success)', background: 'var(--success-bg)', borderRadius: 8, padding: '10px 14px' }}>
                <div style={{ fontWeight: 700, marginBottom: 4 }}>Proyecto creado: {convertResult.project_code}</div>
                <div style={{ color: 'var(--text-2)' }}>{convertResult.message}</div>
                {convertResult.rev_contract_id && (
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--accent)', marginTop: 4 }}>Contrato ASC 606 creado automáticamente</div>
                )}
              </div>
            ) : (
              <>
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.5 }}>
                  Convierte esta oportunidad en un proyecto activo. Se creará automáticamente un contrato ASC 606 con el método de reconocimiento correspondiente al tipo de contrato.
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
  const [detailOpp, setDetailOpp] = useState(null)

  const { data = [], isLoading, isError, error, refetch, isFetching } = usePipeline()
  const createOpportunity = useCreateOpportunity()
  const updateOpportunity = useUpdateOpportunity()
  const deleteOpportunity = useDeleteOpportunity()

  const stageLabels = useMemo(() => ({
    lead: t(STAGE_TRANSLATION_KEYS.lead),
    qualification: t(STAGE_TRANSLATION_KEYS.qualification),
    proposal: t(STAGE_TRANSLATION_KEYS.proposal),
    negotiation: t(STAGE_TRANSLATION_KEYS.negotiation),
    won: t(STAGE_TRANSLATION_KEYS.won),
    lost: t(STAGE_TRANSLATION_KEYS.lost),
    cancelled: 'Cancelada',
  }), [t])

  const owners = useMemo(() => {
    const seen = new Map()
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
    const buckets = Object.fromEntries(STAGES.map((stage) => [stage, []]))
    filtered.forEach((opportunity) => {
      const stage = STAGES.includes(opportunity.stage) ? opportunity.stage : 'lead'
      buckets[stage].push(opportunity)
    })
    return buckets
  }, [filtered])

  const summary = useMemo(() => {
    const open = filtered.filter((item) => !['won', 'lost', 'cancelled'].includes(item.stage))
    const closed = filtered.filter((item) => ['won', 'lost'].includes(item.stage))
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

  async function handleCreate(event) {
    event.preventDefault()
    if (!form.name.trim() || !form.client_name.trim()) {
      toast.error('Nombre y cliente son obligatorios')
      return
    }

    try {
      await createOpportunity.mutateAsync({
        name: form.name.trim(),
        client_name: form.client_name.trim(),
        stage: form.stage,
        probability: Number(form.probability) || 0,
        expected_revenue: form.expected_revenue === '' ? null : Number(form.expected_revenue),
        expected_close_date: form.expected_close_date || null,
        description: form.description.trim() || null,
      })
      toast.success('Oportunidad creada')
      setForm(emptyForm())
      setShowCreate(false)
    } catch (mutationError) {
      toast.error(extractErr(mutationError, 'No se pudo crear la oportunidad'))
    }
  }

  async function handleStageChange(opportunity, nextStage, selectElement) {
    if (!nextStage || nextStage === opportunity.stage) return
    try {
      await updateOpportunity.mutateAsync({ id: opportunity.id, data: { stage: nextStage } })
      toast.success(`Etapa actualizada a ${stageLabels[nextStage] || nextStage}`)
    } catch (mutationError) {
      if (selectElement) selectElement.value = opportunity.stage
      toast.error(extractErr(mutationError, 'No se pudo actualizar la etapa'))
    }
  }

  async function handleDelete(opportunity) {
    if (!window.confirm(`Eliminar la oportunidad ${opportunity.name}?`)) return
    try {
      await deleteOpportunity.mutateAsync(opportunity.id)
      toast.success('Oportunidad eliminada')
    } catch (mutationError) {
      toast.error(extractErr(mutationError, 'No se pudo eliminar la oportunidad'))
    }
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
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Nombre, cliente, código o responsable"
          style={{ flex: '1 1 260px' }}
        />
        <Select
          label="Responsable"
          value={ownerFilter}
          onChange={(event) => setOwnerFilter(event.target.value)}
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
          <div style={{ fontWeight: 700, marginBottom: 8 }}>No se pudo cargar el pipeline</div>
          <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginBottom: 14 }}>{extractErr(error, 'Error inesperado')}</div>
          <Button onClick={() => refetch()} loading={isFetching}>Reintentar</Button>
        </div>
      ) : null}

      {!isLoading && !isError && filtered.length === 0 ? (
        <div style={{ ...panelStyle, padding: 28 }}>
          <EmptyState
            icon="chart"
            title="No hay oportunidades visibles"
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
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 4 }}>
                      {opportunities.length} oportunidad(es) · {fmtCurrency(totalStageRevenue)}
                    </div>
                  </div>
                  <Badge label={stage} display={opportunities.length} />
                </div>

                <div style={{ display: 'grid', gap: 10 }}>
                  {opportunities.length === 0 ? (
                    <div style={{ border: '1px dashed var(--surface-4)', borderRadius: 12, padding: 16, fontSize: "var(--text-sm)", color: 'var(--text-3)', textAlign: 'center' }}>
                      Sin oportunidades en esta etapa
                    </div>
                  ) : opportunities.map((opportunity) => {
                    const allowedStages = [opportunity.stage, ...STAGE_TRANSITIONS[opportunity.stage]]
                    const proposalStatus = opportunity.proposal_status || 'none'
                    const psCfg = PROPOSAL_STATUS_COLORS[proposalStatus]
                    return (
                      <Card key={opportunity.id} style={{ padding: 14, display: 'grid', gap: 10 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'start' }}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{opportunity.name}</div>
                            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{opportunity.client_name || 'Sin cliente'}</div>
                            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 4 }}>{opportunity.code || 'Sin código'}</div>
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
                            <strong style={{ color: 'var(--text-1)' }}>{fmtCurrency(opportunity.expected_revenue)}</strong>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                            <span>Probabilidad</span>
                            <strong style={{ color: 'var(--text-1)' }}>{fmtPct(opportunity.probability)}</strong>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                            <span>Ponderado</span>
                            <strong style={{ color: 'var(--warning)' }}>{fmtCurrency(opportunity.weighted_revenue)}</strong>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                            <span>Cierre</span>
                            <strong style={{ color: 'var(--text-1)' }}>{fmtDate(opportunity.expected_close_date)}</strong>
                          </div>
                        </div>

                        {/* Proposal status indicator */}
                        {proposalStatus !== 'none' && (
                          <div style={{ fontSize: "var(--text-xs)", padding: '3px 8px', borderRadius: 6, background: psCfg.bg, color: psCfg.color, fontWeight: 600, width: 'fit-content' }}>
                            {psCfg.label}
                          </div>
                        )}

                        <div style={{ display: 'grid', gap: 8 }}>
                          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
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
                                <option key={allowedStage} value={allowedStage}>
                                  {stageLabels[allowedStage] || allowedStage}
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
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Input
              label={t('pipeline.opportunity_name')}
              value={form.name}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
              required
            />
            <Input
              label={t('pipeline.client_name')}
              value={form.client_name}
              onChange={(event) => setForm((current) => ({ ...current, client_name: event.target.value }))}
              required
            />
            <Input
              label={t('pipeline.value')}
              type="number"
              value={form.expected_revenue}
              onChange={(event) => setForm((current) => ({ ...current, expected_revenue: event.target.value }))}
            />
            <Input
              label={t('pipeline.probability')}
              type="number"
              value={form.probability}
              onChange={(event) => setForm((current) => ({ ...current, probability: event.target.value }))}
            />
            <Select
              label={t('pipeline.stage')}
              value={form.stage}
              onChange={(event) => setForm((current) => ({ ...current, stage: event.target.value }))}
              options={STAGES.map((stage) => ({ value: stage, label: stageLabels[stage] || stage }))}
            />
            <Input
              label={t('pipeline.expected_close')}
              type="date"
              value={form.expected_close_date}
              onChange={(event) => setForm((current) => ({ ...current, expected_close_date: event.target.value }))}
            />
          </div>

          <div>
            <label style={fieldLabelStyle}>Descripción</label>
            <textarea
              value={form.description}
              onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
              rows={4}
              style={{ ...fieldStyle, resize: 'vertical' }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
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
