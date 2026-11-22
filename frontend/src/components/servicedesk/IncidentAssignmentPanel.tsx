/**
 * IncidentAssignmentPanel — recomendación de agente o cola por reglas ponderadas (sin modelo entrenado).
 *
 * Backend endpoints:
 *   GET  /sd/assignment/stats
 *     -> {
 *          total_recommendations, last_recommendation_at, lgbm_available,
 *          total_unassigned,
 *          agent_loads: [{user_id, agent_id, name, agent_name, open_tickets,
 *                          active_tickets, capacity, specializations, is_on_call, groups}],
 *        }
 *   POST /sd/tickets/{id}/recommend-assignment
 *     -> {
 *          recommended_user_id, recommended_name, confidence, all_scores: [
 *            {user_id, name, score, available, components: {availability, historical_speed, historical_csat, skill_match}}
 *          ], method_used, reasoning, lgbm_available,
 *        }
 * Tipos: SdEstadisticasDeAsignacion y SdRecomendacionDeAsignacion (services/api/tipos-sd.ts).
 *
 * 16-11-2026 (pasada de diseño): rehecho con Card + Section, campos del kit
 * (`campo-form`), StatusBadge y EmptyState con icono lucide (era un emoji 📊).
 * Fuera los textos fijos («Ticket ID (uuid)», «disp.», «skills», «Error al…»,
 * «Tickets abiertos» del gráfico) y el código del método a pelo.
 */
import { etiquetaDelTema, tooltipDelTemaConBorde } from '../../constants/estilosGrafico'
import { useId, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { incidentAssignmentApi, ticketsApi, type ApiError } from '../../services/api'
import type { SdRecomendacionDeAsignacion } from '../../services/api/tipos-sd'
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { useChartTheme } from '../../charts/useChartTheme'
import { BarChart3, CheckCircle2, Sparkles, UserCheck } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { Card, Button, Select, Spinner, EmptyState, Section, Input, Textarea } from '../ui'
import StatusBadge from '../ui/StatusBadge'
import { POLL_FREQUENT_MS } from '../../constants/timings'
import './IncidentAssignmentPanel.css'

const pct = (v: number | null | undefined) => Math.round((v ?? 0) * 100)

export default function IncidentAssignmentPanel() {
  const t = useAppT()
  const id = useId()
  const { tokens } = useChartTheme()
  const [ticketId, setTicketId] = useState<string>('')
  const [ticketTitle, setTicketTitle] = useState<string>('')
  const [ticketDescription, setTicketDescription] = useState<string>('')
  const [priority, setPriority] = useState<string>('p3_medium')
  const [recommendation, setRecommendation] = useState<SdRecomendacionDeAsignacion | null>(null)
  const [applySuccess, setApplySuccess] = useState<boolean>(false)

  const { data: stats, isLoading: statsLoading, refetch: refetchStats } = useQuery({
    queryKey: ['incident-assign-stats'],
    queryFn: () => incidentAssignmentApi.stats().then(r => r.data),
    refetchInterval: POLL_FREQUENT_MS,
  })

  const candidates = stats?.agent_loads ?? []

  const recommendMutation = useMutation<SdRecomendacionDeAsignacion, ApiError, string>({
    mutationFn: (tid) => {
      const candidate_agents = candidates.map((a) => ({
        user_id: a.user_id,
        name: a.name,
        active_tickets: a.active_tickets,
        capacity: a.capacity,
        specializations: a.specializations,
        is_on_call: a.is_on_call,
      }))
      return ticketsApi.recommendAssignment(tid, {
        title: ticketTitle || tid,
        description: ticketDescription || '',
        priority,
        ticket_type: 'incident',
        candidate_agents,
      }).then(r => r.data)
    },
    onSuccess: (data) => {
      setRecommendation(data)
      setApplySuccess(false)
      refetchStats()
    },
  })

  const applyMutation = useMutation<unknown, ApiError, { ticketId: string; userId: string }>({
    mutationFn: ({ ticketId: tid, userId }) => ticketsApi.update(tid, { assigned_to_user_id: userId }),
    onSuccess: () => {
      setApplySuccess(true)
      refetchStats()
    },
  })

  const allScores = recommendation?.all_scores ?? []

  return (
    <Card>
      <Section
        title={<span className="iap-titulo"><UserCheck size={16} aria-hidden="true" />{t('incidentassignment.titulo')}</span>}
        subtitle={t('incidentassignment.desc')}
        actions={<>
          <StatusBadge kind="neutral" caps={false}>{t('sd_cfg.assign_rules')}</StatusBadge>
          {stats?.total_recommendations != null && (
            <span className="u-text3-xs">
              {t('incidentassignment.resumen', { recomendaciones: stats.total_recommendations, sin_asignar: stats.total_unassigned ?? 0 })}
            </span>
          )}
        </>}
      >
        <div className="iap-grid">
          {/* Pedir recomendación */}
          <div className="u-stack-12">
            <div className="ds-eyebrow">{t('incidentassignment.pedir')}</div>
            <div className="ui-field">
              <label htmlFor={`${id}-ticket`} className="campo-etiqueta">{t('incidentassignment.ticket_id')}</label>
              <Input id={`${id}-ticket`} type="text" value={ticketId} onChange={e => setTicketId(e.target.value)} inputClassName="campo-form" />
            </div>
            <div className="ui-field">
              <label htmlFor={`${id}-titulo`} className="campo-etiqueta">{t('incidentassignment.titulo_incidencia')}</label>
              <Input id={`${id}-titulo`} type="text" value={ticketTitle} onChange={e => setTicketTitle(e.target.value)} inputClassName="campo-form" />
            </div>
            <div className="ui-field">
              <label htmlFor={`${id}-desc`} className="campo-etiqueta">{t('incidentassignment.descripcion')}</label>
              <Textarea id={`${id}-desc`} value={ticketDescription} onChange={e => setTicketDescription(e.target.value)} rows={2} inputClassName="campo-form iap-textarea" />
              <div className="u-text3-xs">{t('incidentassignment.descripcion_hint')}</div>
            </div>
            <div className="iap-fila">
              <div className="ui-field iap-fila__campo">
                <label htmlFor={`${id}-prio`} className="campo-etiqueta">{t('service_desk.ticket_priority')}</label>
                <Select suelto placeholder={false} id={`${id}-prio`} value={priority} onChange={e => setPriority(e.target.value)} className="campo-form">
                  <option value="p1_critical">{t('service_desk.priority_p1')}</option>
                  <option value="p2_high">{t('service_desk.priority_p2')}</option>
                  <option value="p3_medium">{t('service_desk.priority_p3')}</option>
                  <option value="p4_low">{t('service_desk.priority_p4')}</option>
                </Select>
              </div>
              <Button
                icon={<Sparkles size={14} />}
                onClick={() => ticketId.trim() && recommendMutation.mutate(ticketId.trim())}
                disabled={!ticketId.trim() || recommendMutation.isPending || !candidates.length}
                loading={recommendMutation.isPending}
              >
                {t('incidentassignment.recomendar')}
              </Button>
            </div>

            {!candidates.length && !statsLoading && (
              <div className="iap-aviso" role="status">{t('incidentassignment.sin_agentes')}</div>
            )}
            {recommendMutation.isError && (
              <div className="iap-aviso iap-aviso--error" role="alert">
                {recommendMutation.error?.response?.data?.detail || t('incidentassignment.error_recomendar')}
              </div>
            )}

            {recommendation && (
              recommendation.recommended_user_id ? (
                <div className="iap-resultado">
                  <div className="ds-eyebrow">{t('incidentassignment.recomendado')}</div>
                  <div className="iap-resultado__nombre">
                    <span>{recommendation.recommended_name}</span>
                    <StatusBadge kind="accent" caps={false}>{t('incidentassignment.confianza', { p: pct(recommendation.confidence) })}</StatusBadge>
                  </div>
                  {recommendation.reasoning && <div className="u-text2-sm">{recommendation.reasoning}</div>}
                  <div className="u-text3-xs">
                    {t('incidentassignment.metodo')} {etiquetaCodigo(t, 'incidentassignment.metodo_v', recommendation.method_used)}
                  </div>
                  <div className="u-wrap-center-8">
                    {applySuccess ? (
                      <StatusBadge kind="success" caps={false}><CheckCircle2 size={12} aria-hidden="true" /> {t('incidentassignment.ticket_asignado_correctamente')}</StatusBadge>
                    ) : (
                      <Button
                        icon={<CheckCircle2 size={14} />}
                        onClick={() => applyMutation.mutate({ ticketId: ticketId.trim(), userId: recommendation.recommended_user_id })}
                        disabled={applyMutation.isPending || !ticketId.trim()}
                        loading={applyMutation.isPending}
                      >
                        {t('incidentassignment.aplicar_asignacion')}
                      </Button>
                    )}
                  </div>
                  {applyMutation.isError && (
                    <div className="iap-aviso iap-aviso--error" role="alert">
                      {applyMutation.error?.response?.data?.detail || t('incidentassignment.error_aplicar')}
                    </div>
                  )}
                </div>
              ) : (
                <div className="iap-aviso" role="status">{t('incidentassignment.sin_recomendacion')}</div>
              )
            )}

            {allScores.length > 0 && (
              <div className="u-stack-8">
                <div className="ds-eyebrow">{t('incidentassignment.candidatos')}</div>
                <ul className="iap-lista">
                  {allScores.slice(0, 5).map((rec, i) => {
                    const score = pct(rec.score)
                    // Auditoría 2026-11: leía `kw_score`, `workload_score`, `is_on_call` y
                    // `active_tickets`, que la recomendación no trae: el desglose son los
                    // `components` de la puntuación y la carga sale de `agent_loads`.
                    const c = rec.components
                    const desglose = [
                      t('incidentassignment.comp_disponibilidad', { p: pct(c.availability) }),
                      t('incidentassignment.comp_rapidez', { p: pct(c.historical_speed) }),
                      t('incidentassignment.comp_satisfaccion', { p: pct(c.historical_csat) }),
                      t('incidentassignment.comp_conocimientos', { p: pct(c.skill_match) }),
                    ]
                    const carga = candidates.find(a => a.user_id === rec.user_id)
                    return (
                      <li key={rec.user_id || i} className="iap-candidato">
                        <div className="u-flex1-min0">
                          <div className="u-text1-sm-600">{rec.name || rec.user_id}</div>
                          <div className="u-text3-xs">{desglose.join(' · ')}</div>
                        </div>
                        {carga && <span className="u-text3-xs">{t('incidentassignment.n_tickets', { n: carga.open_tickets })}</span>}
                        <StatusBadge kind={score >= 75 ? 'success' : score >= 50 ? 'warning' : 'neutral'} caps={false}>{score} %</StatusBadge>
                      </li>
                    )
                  })}
                </ul>
              </div>
            )}
          </div>

          {/* Carga por agente */}
          <div className="u-stack-12">
            <div className="ds-eyebrow iap-titulo"><BarChart3 size={14} aria-hidden="true" />{t('incidentassignment.carga')}</div>
            {statsLoading ? (
              <div className="iap-cargando"><Spinner /></div>
            ) : !candidates.length ? (
              <EmptyState icon={<BarChart3 size={28} />} title={t('incidentassignment.sin_agentes_registrados')} description={t('incidentassignment.sin_agentes_desc')} />
            ) : (
              <div className="iap-grafico">
                <ResponsiveContainer width="100%" height={Math.max(180, Math.min(candidates.length, 12) * 28)}>
                  <BarChart data={candidates.slice(0, 12)} layout="vertical" margin={{ left: 8, right: 8 }}>
                    <XAxis type="number" tick={{ fontSize: 10, fill: tokens.textColor }} allowDecimals={false} />
                    <YAxis dataKey="agent_name" type="category" width={120} tick={{ fontSize: 10, fill: tokens.textColor }} />
                    <Tooltip contentStyle={tooltipDelTemaConBorde(tokens)} labelStyle={etiquetaDelTema(tokens)} />
                    <Bar dataKey="open_tickets" name={t('incidentassignment.tickets_abiertos')} fill="var(--accent)" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
            {stats?.total_unassigned != null && (
              <div className="u-wrap-center-8">
                <StatusBadge kind={stats.total_unassigned > 0 ? 'warning' : 'success'} caps={false}>
                  {t('incidentassignment.sin_asignar', { n: stats.total_unassigned })}
                </StatusBadge>
              </div>
            )}
          </div>
        </div>
      </Section>
    </Card>
  )
}
