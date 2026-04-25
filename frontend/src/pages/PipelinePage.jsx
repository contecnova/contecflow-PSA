import { useMemo, useState } from 'react'
import { Megaphone, Plus, Trash2 } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import PageHeader from '../components/layout/PageHeader'
import { Badge, Button, Card, EmptyState, Input, Modal, Select, Spinner } from '../components/ui'
import { useCreateOpportunity, useDeleteOpportunity, usePipeline, useUpdateOpportunity } from '../hooks/usePipeline'
import { useToast } from '../context/ToastContext'
import { extractErr, fmtCurrency, fmtDate, fmtPct } from '../utils/helpers'

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

const panelStyle = {
  background: 'var(--surface-2)',
  border: '1px solid var(--surface-4)',
  borderRadius: 16,
}

const fieldLabelStyle = {
  fontSize: 11,
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
  fontSize: 13,
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

function SummaryCard({ label, value, tone = 'var(--text-1)', subvalue }) {
  return (
    <Card style={{ minWidth: 180, padding: 18 }}>
      <div style={{ fontSize: 11, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 800, color: tone, lineHeight: 1, marginBottom: subvalue ? 6 : 0 }}>
        {value}
      </div>
      {subvalue ? <div style={{ fontSize: 12, color: 'var(--text-3)' }}>{subvalue}</div> : null}
    </Card>
  )
}

export default function PipelinePage() {
  const t = useAppT()
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [ownerFilter, setOwnerFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState(() => emptyForm())

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
    <div style={{ padding: 32, display: 'grid', gap: 18 }}>
      <PageHeader icon={<Megaphone size={18} />} title={t('pipeline.title')} subtitle={t('pipeline.subtitle')} />

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
          <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 14 }}>{extractErr(error, 'Error inesperado')}</div>
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
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 14, alignItems: 'start' }}>
          {STAGES.map((stage) => {
            const opportunities = grouped[stage] || []
            const totalStageRevenue = opportunities.reduce((acc, item) => acc + (item.expected_revenue || 0), 0)
            return (
              <section key={stage} style={{ ...panelStyle, padding: 14, minHeight: 180 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14, gap: 12 }}>
                  <div>
                    <div style={{ fontSize: 12, color: STAGE_COLORS[stage], fontWeight: 800, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                      {stageLabels[stage] || stage}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
                      {opportunities.length} oportunidad(es) · {fmtCurrency(totalStageRevenue)}
                    </div>
                  </div>
                  <Badge label={stage} display={opportunities.length} />
                </div>

                <div style={{ display: 'grid', gap: 10 }}>
                  {opportunities.length === 0 ? (
                    <div style={{ border: '1px dashed var(--surface-4)', borderRadius: 12, padding: 16, fontSize: 12, color: 'var(--text-3)', textAlign: 'center' }}>
                      Sin oportunidades en esta etapa
                    </div>
                  ) : opportunities.map((opportunity) => {
                    const allowedStages = [opportunity.stage, ...STAGE_TRANSITIONS[opportunity.stage]]
                    return (
                      <Card key={opportunity.id} style={{ padding: 14, display: 'grid', gap: 10 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'start' }}>
                          <div>
                            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>{opportunity.name}</div>
                            <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{opportunity.client_name || 'Sin cliente'}</div>
                            <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>{opportunity.code || 'Sin código'}</div>
                          </div>
                          <button
                            type="button"
                            onClick={() => handleDelete(opportunity)}
                            title="Eliminar oportunidad"
                            style={{ background: 'transparent', border: 'none', color: 'var(--danger)', cursor: 'pointer', padding: 2 }}
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>

                        <div style={{ display: 'grid', gap: 6, fontSize: 12, color: 'var(--text-2)' }}>
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

                        <div style={{ display: 'grid', gap: 8 }}>
                          <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
                            Responsable: {opportunity.owner_name || 'Sin asignar'}
                          </div>
                          <label style={{ display: 'grid', gap: 6 }}>
                            <span style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Mover a etapa</span>
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
                          <div style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.45, borderTop: '1px solid var(--surface-4)', paddingTop: 10 }}>
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
    </div>
  )
}
