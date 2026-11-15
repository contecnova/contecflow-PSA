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
 */
import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { incidentAssignmentApi, ticketsApi, type ApiError } from '../../services/api'
import type { SdRecomendacionDeAsignacion } from '../../services/api/tipos-sd'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import { UserCheck, BarChart2 } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { Card, Button, Spinner, EmptyState } from '../ui'
import { POLL_FREQUENT_MS } from '../../constants/timings'
import './IncidentAssignmentPanel.css'


export default function IncidentAssignmentPanel() {
  const t = useAppT()
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
    mutationFn: (id) => {
      const candidate_agents = candidates.map((a) => ({
        user_id: a.user_id,
        name: a.name,
        active_tickets: a.active_tickets,
        capacity: a.capacity,
        specializations: a.specializations,
        is_on_call: a.is_on_call,
      }))
      return ticketsApi.recommendAssignment(id, {
        title: ticketTitle || `Incident ${id}`,
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
    mutationFn: ({ ticketId, userId }) =>
      ticketsApi.update(ticketId, { assigned_to_user_id: userId }),
    onSuccess: () => {
      setApplySuccess(true)
      refetchStats()
    },
  })

  const allScores = recommendation?.all_scores ?? []
  const lgbmAvailable = stats?.lgbm_available ?? recommendation?.lgbm_available ?? false

  return (
    <Card style={{ padding: '20px 22px' }}>
      <div className="inaspa-row-1">
        <div className="u-row-center-8">
          <UserCheck size={18} style={{ color: 'var(--accent)' }} />
          <h2 className="inaspa-box-1">
            {t('sd.assign.title', 'Asignación inteligente de incidencias')}
          </h2>
        </div>
        <div className="u-row-center-8">
          <span className="inaspa-box-12" style={{ color: lgbmAvailable ? 'var(--success)' : 'var(--text-3)', background: lgbmAvailable
              ? 'color-mix(in srgb, var(--success) 12%, transparent)'
              : 'var(--surface-3)', border: `1px solid ${lgbmAvailable ? 'color-mix(in srgb, var(--success) 30%, transparent)' : 'var(--surface-4)'}`, borderRadius: 'var(--radius-full, 999px)' }}>
            {t('sd_cfg.assign_rules')}
          </span>
          {stats?.total_recommendations != null && (
            <span className="u-text3-xs">
              {stats.total_recommendations} recomendaciones · {stats.total_unassigned ?? 0} {t('incidentassignment.sin_asignar')}
            </span>
          )}
        </div>
      </div>

      <div className="inaspa-grid-1">
        {/* Recommendation column */}
        <div>
          <div className="inaspa-fieldlabel">{t('sd.assign.get_recommendations', 'Pedir recomendación')}</div>

          <div className="inaspa-stack-1">
            <input aria-label="Ticket ID (uuid)"
              type="text"
              placeholder="Ticket ID (uuid)"
              value={ticketId}
              onChange={e => setTicketId(e.target.value)}
              className="inaspa-inputbase"
            />
            <input aria-label={t('incidentassignment.titulo_de_la_incidencia_opcional')}
              type="text"
              placeholder={t('incidentassignment.titulo_de_la_incidencia_opcional')}
              value={ticketTitle}
              onChange={e => setTicketTitle(e.target.value)}
              className="inaspa-inputbase"
            />
            <textarea aria-label={t('incidentassignment.descripcion_palabras_clave_opcional_ayuda_al_matching')}
              placeholder={t('incidentassignment.descripcion_palabras_clave_opcional_ayuda_al_matching')}
              value={ticketDescription}
              onChange={e => setTicketDescription(e.target.value)}
              rows={2}
              className="inaspa-inputbase2"
            />
            <div className="u-row-8">
              <select value={priority} onChange={e => setPriority(e.target.value)} className="inaspa-inputbase3">
                <option value="p1_critical">{t('incidentassignment.p1_critico')}</option>
                <option value="p2_high">P2 Alto</option>
                <option value="p3_medium">P3 Medio</option>
                <option value="p4_low">P4 Bajo</option>
              </select>
              <Button
                onClick={() => ticketId && recommendMutation.mutate(ticketId.trim())}
                disabled={!ticketId.trim() || recommendMutation.isPending || !candidates.length}
                loading={recommendMutation.isPending}
                style={{ flex: 1 }}
              >
                {t('sd.assign.recommend', 'Recomendar agente')}
              </Button>
            </div>
          </div>

          {!candidates.length && !statsLoading && (
            <div className="inaspa-box-2">
              {t('incidentassignment.no_hay_agentes_disponibles_crea_grupos_y')}
            </div>
          )}

          {recommendation && (
            <div>
              {recommendation.recommended_user_id ? (
                <div className="inaspa-box-3">
                  <div className="inaspa-box-4">
                    Recomendado
                  </div>
                  <div className="inaspa-txt-1">
                    {recommendation.recommended_name}
                    <span className="inaspa-box-5">
                      {Math.round(recommendation.confidence * 100)}%
                    </span>
                  </div>
                  {recommendation.reasoning && (
                    <div className="inaspa-box-6">
                      {recommendation.reasoning}
                    </div>
                  )}
                  <div className="inaspa-box-7">
                    {t('incidentassignment.metodo')} <span className="u-mono">{recommendation.method_used}</span>
                  </div>
                  <div className="inaspa-sp-1">
                    {applySuccess ? (
                      <div className="inaspa-txt-2">
                        ✓ Ticket asignado correctamente
                      </div>
                    ) : (
                      <Button
                        onClick={() => applyMutation.mutate({ ticketId: ticketId.trim(), userId: recommendation.recommended_user_id })}
                        disabled={applyMutation.isPending || !ticketId.trim()}
                        loading={applyMutation.isPending}
                        style={{ fontSize: 'var(--text-sm)' }}
                      >
                        {t('incidentassignment.aplicar_asignacion')}
                      </Button>
                    )}
                    {applyMutation.isError && (
                      <div className="inaspa-box-8">
                        {applyMutation.error?.response?.data?.detail || 'Error al aplicar asignación'}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="inaspa-box-9">
                  {t('incidentassignment.no_se_ha_podido_recomendar_ningun_agente')}
                </div>
              )}

              {allScores.length > 0 && (
                <>
                  <div className="inaspa-fieldlabel">{t('sd.assign.top_agents', 'Top candidatos')}</div>
                  <div className="u-stack-6">
                    {allScores.slice(0, 5).map((rec, i) => {
                      const score = Math.round(rec.score * 100)
                      const scoreColor = score >= 75 ? 'var(--success)' : score >= 50 ? 'var(--warning)' : 'var(--text-3)'
                      // Auditoría 2026-11: leía `kw_score`, `workload_score`, `is_on_call` y
                      // `active_tickets`, que la recomendación no trae: el desglose son los
                      // `components` de la puntuación y la carga sale de `agent_loads`.
                      const c = rec.components
                      const breakdown = [
                        `disp. ${Math.round(c.availability * 100)}%`,
                        `rapidez ${Math.round(c.historical_speed * 100)}%`,
                        `CSAT ${Math.round(c.historical_csat * 100)}%`,
                        `skills ${Math.round(c.skill_match * 100)}%`,
                      ]
                      const carga = candidates.find(a => a.user_id === rec.user_id)
                      return (
                        <div key={rec.user_id || i} className="inaspa-row-2">
                          <div className="u-flex1-min0">
                            <div className="u-text1-sm-600">
                              {rec.name || rec.user_id}
                            </div>
                            <div className="u-text3-xs-mt2">
                              {breakdown.join(' · ')}
                            </div>
                          </div>
                          <div className="inaspa-row-3">
                            {carga && (
                              <span className="u-text3-xs">
                                {carga.open_tickets} tickets
                              </span>
                            )}
                            <span className="inaspa-box-13" style={{ color: scoreColor, background: `color-mix(in srgb, ${scoreColor} 15%, transparent)`, border: `1px solid color-mix(in srgb, ${scoreColor} 30%, transparent)`, borderRadius: 'var(--radius-sm)' }}>{score}%</span>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </>
              )}
            </div>
          )}

          {recommendMutation.isError && (
            <div className="inaspa-box-10">
              {recommendMutation.error?.response?.data?.detail || 'Error al obtener recomendación'}
            </div>
          )}
        </div>

        {/* Stats column */}
        <div>
          <div className="inaspa-row-4">
            <BarChart2 size={14} style={{ color: 'var(--purple)' }} />
            <span className="inaspa-txt-3">
              {t('sd.assign.load_by_agent', 'Carga por agente (tickets abiertos)')}
            </span>
          </div>

          {statsLoading ? (
            <div className="inaspa-row-5"><Spinner /></div>
          ) : !candidates.length ? (
            <EmptyState icon="📊" title={t('incidentassignment.sin_agentes_registrados')} />
          ) : (
            <div className="inaspa-box-11">
              <ResponsiveContainer width="100%" height={Math.max(180, candidates.length * 28)}>
                <BarChart data={candidates.slice(0, 12)} layout="vertical" margin={{ left: 8, right: 8 }}>
                  <XAxis type="number" tick={{ fontSize: 10, fill: tokens.textColor }} allowDecimals={false} />
                  <YAxis dataKey="agent_name" type="category" width={120} tick={{ fontSize: 10, fill: tokens.textColor }} />
                  <Tooltip
                    contentStyle={{
                      background: tokens.tooltipBg,
                      border: '1px solid var(--surface-4)',
                      borderRadius: 8,
                    }}
                    labelStyle={{ color: tokens.textColor }}
                  />
                  <Bar dataKey="open_tickets" name="Tickets abiertos" fill="var(--accent)" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {stats?.total_unassigned != null && (
            <div className="inaspa-row-6">
              <span className="inaspa-txt-4" style={{ color: stats.total_unassigned > 0 ? 'var(--warning)' : 'var(--success)' }}>{stats.total_unassigned}</span>
              {t('sd.assign.unassigned', 'tickets sin asignar')}
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}
