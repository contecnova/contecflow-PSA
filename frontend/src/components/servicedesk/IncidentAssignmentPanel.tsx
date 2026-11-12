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
 *            {user_id, name, score, kw_score, workload_score, is_on_call, active_tickets}
 *          ], method_used, reasoning, lgbm_available,
 *        }
 */
import React, { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { incidentAssignmentApi, ticketsApi } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import { UserCheck, BarChart2 } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { Card, Button, Spinner, EmptyState } from '../ui'

// TODO type: incidentAssignmentApi payloads — needs shared types
interface AgentScore {
  user_id: string | number
  name: string
  score: number
  kw_score?: number
  workload_score?: number
  is_on_call?: boolean
  active_tickets?: number
}

interface Recommendation {
  recommended_user_id?: string | number
  recommended_name?: string
  confidence?: number
  all_scores?: AgentScore[]
  method_used?: string
  reasoning?: string
  lgbm_available?: boolean
}

interface AgentLoad {
  user_id: string | number
  agent_id?: string | number
  name?: string
  agent_name?: string
  open_tickets?: number
  active_tickets?: number
  capacity?: number
  specializations?: string[]
  is_on_call?: boolean
  groups?: string[]
}

interface AssignmentStats {
  total_recommendations?: number
  last_recommendation_at?: string
  lgbm_available?: boolean
  total_unassigned?: number
  agent_loads?: AgentLoad[]
}

const fieldLabel: React.CSSProperties = {
  fontSize: 'var(--text-2xs)',
  fontWeight: 700,
  color: 'var(--text-3)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 6,
}
const inputBase: React.CSSProperties = {
  width: '100%',
  background: 'var(--surface-3)',
  border: '1px solid var(--surface-4)',
  borderRadius: 8,
  padding: '8px 12px',
  color: 'var(--text-1)',
  fontSize: 'var(--text-sm)',
  fontFamily: 'inherit',
  outline: 'none',
  boxSizing: 'border-box',
}

export default function IncidentAssignmentPanel() {
  const t = useAppT()
  const { tokens } = useChartTheme()
  const [ticketId, setTicketId] = useState<string>('')
  const [ticketTitle, setTicketTitle] = useState<string>('')
  const [ticketDescription, setTicketDescription] = useState<string>('')
  const [priority, setPriority] = useState<string>('p3_medium')
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null)

  const [applySuccess, setApplySuccess] = useState<boolean>(false)

  const { data: stats, isLoading: statsLoading, refetch: refetchStats } = useQuery<AssignmentStats>({
    queryKey: ['incident-assign-stats'],
    queryFn: () => incidentAssignmentApi.stats().then(r => r.data),
    refetchInterval: 30_000,
  })

  const candidates = stats?.agent_loads ?? []

  const recommendMutation = useMutation<Recommendation, unknown, string>({
    mutationFn: (id) => {
      const candidate_agents = candidates.map((a) => ({
        user_id: String(a.user_id ?? a.agent_id),
        name: a.name ?? a.agent_name ?? a.user_id,
        active_tickets: Number(a.active_tickets ?? a.open_tickets ?? 0),
        capacity: Number(a.capacity ?? 10),
        specializations: Array.isArray(a.specializations) ? a.specializations : [],
        is_on_call: Boolean(a.is_on_call ?? false),
      }))
      return ticketsApi.recommendAssignment(id, {
        title: ticketTitle || `Incident ${id}`,
        description: ticketDescription || '',
        priority,
        ticket_type: 'incident',
        candidate_agents,
      }).then(r => r.data as Recommendation)
    },
    onSuccess: (data) => {
      setRecommendation(data)
      setApplySuccess(false)
      refetchStats()
    },
  })

  const applyMutation = useMutation<unknown, unknown, { ticketId: string; userId: string | number | undefined }>({
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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <div className="u-row-center-8">
          <UserCheck size={18} style={{ color: 'var(--accent)' }} />
          <h2 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', margin: 0 }}>
            {t('sd.assign.title', 'Asignación inteligente de incidencias')}
          </h2>
        </div>
        <div className="u-row-center-8">
          <span style={{
            fontSize: 'var(--text-2xs)', fontWeight: 700, textTransform: 'uppercase',
            letterSpacing: '0.05em',
            color: lgbmAvailable ? 'var(--success)' : 'var(--text-3)',
            background: lgbmAvailable
              ? 'color-mix(in srgb, var(--success) 12%, transparent)'
              : 'var(--surface-3)',
            border: `1px solid ${lgbmAvailable ? 'color-mix(in srgb, var(--success) 30%, transparent)' : 'var(--surface-4)'}`,
            borderRadius: 'var(--radius-full, 999px)',
            padding: '2px 9px',
          }}>
            {t('sd_cfg.assign_rules')}
          </span>
          {stats?.total_recommendations != null && (
            <span className="u-text3-xs">
              {stats.total_recommendations} recomendaciones · {stats.total_unassigned ?? 0} {t('incidentassignment.sin_asignar')}
            </span>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 18 }}>
        {/* Recommendation column */}
        <div>
          <div style={fieldLabel}>{t('sd.assign.get_recommendations', 'Pedir recomendación')}</div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10 }}>
            <input
              type="text"
              placeholder="Ticket ID (uuid)"
              value={ticketId}
              onChange={e => setTicketId(e.target.value)}
              style={inputBase}
            />
            <input
              type="text"
              placeholder={t('incidentassignment.titulo_de_la_incidencia_opcional')}
              value={ticketTitle}
              onChange={e => setTicketTitle(e.target.value)}
              style={inputBase}
            />
            <textarea
              placeholder={t('incidentassignment.descripcion_palabras_clave_opcional_ayuda_al_matching')}
              value={ticketDescription}
              onChange={e => setTicketDescription(e.target.value)}
              rows={2}
              style={{ ...inputBase, resize: 'vertical' }}
            />
            <div className="u-row-8">
              <select value={priority} onChange={e => setPriority(e.target.value)} style={{ ...inputBase, flex: '0 0 180px' }}>
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
            <div style={{
              fontSize: 'var(--text-xs)', color: 'var(--text-3)',
              background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
              borderRadius: 8, padding: '8px 12px', marginBottom: 12,
            }}>
              {t('incidentassignment.no_hay_agentes_disponibles_crea_grupos_y')}
            </div>
          )}

          {recommendation && (
            <div>
              {recommendation.recommended_user_id ? (
                <div style={{
                  background: 'color-mix(in srgb, var(--success) 8%, var(--surface-3))',
                  border: '1px solid color-mix(in srgb, var(--success) 30%, var(--surface-4))',
                  borderRadius: 10, padding: '10px 14px', marginBottom: 10,
                }}>
                  <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>
                    Recomendado
                  </div>
                  <div style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--text-1)' }}>
                    {recommendation.recommended_name}
                    <span style={{ marginLeft: 10, fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--success)' }}>
                      {Math.round((recommendation.confidence ?? 0) * 100)}%
                    </span>
                  </div>
                  {recommendation.reasoning && (
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)', marginTop: 4 }}>
                      {recommendation.reasoning}
                    </div>
                  )}
                  <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', marginTop: 4 }}>
                    {t('incidentassignment.metodo')} <span style={{ fontFamily: 'var(--font-mono)' }}>{recommendation.method_used}</span>
                  </div>
                  <div style={{ marginTop: 10 }}>
                    {applySuccess ? (
                      <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--success)' }}>
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
                      <div style={{ marginTop: 6, fontSize: 'var(--text-xs)', color: 'var(--danger)' }}>
                        {(applyMutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Error al aplicar asignación'}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div style={{
                  fontSize: 'var(--text-sm)', color: 'var(--warning)',
                  background: 'color-mix(in srgb, var(--warning) 12%, transparent)',
                  border: '1px solid color-mix(in srgb, var(--warning) 30%, transparent)',
                  borderRadius: 8, padding: '8px 12px', marginBottom: 10,
                }}>
                  {t('incidentassignment.no_se_ha_podido_recomendar_ningun_agente')}
                </div>
              )}

              {allScores.length > 0 && (
                <>
                  <div style={fieldLabel}>{t('sd.assign.top_agents', 'Top candidatos')}</div>
                  <div className="u-stack-6">
                    {allScores.slice(0, 5).map((rec, i) => {
                      const score = Math.round((rec.score ?? 0) * 100)
                      const scoreColor = score >= 75 ? 'var(--success)' : score >= 50 ? 'var(--warning)' : 'var(--text-3)'
                      const breakdown = []
                      if (rec.kw_score != null) breakdown.push(`kw ${Math.round(rec.kw_score * 100)}%`)
                      if (rec.workload_score != null) breakdown.push(`carga ${Math.round(rec.workload_score * 100)}%`)
                      if (rec.is_on_call) breakdown.push('on-call')
                      return (
                        <div key={rec.user_id || i} style={{
                          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                          padding: '10px 14px',
                          background: 'var(--surface-3)',
                          border: '1px solid var(--surface-4)',
                          borderRadius: 8,
                        }}>
                          <div className="u-flex1-min0">
                            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-1)' }}>
                              {rec.name ?? rec.user_id}
                            </div>
                            {breakdown.length > 0 && (
                              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 2 }}>
                                {breakdown.join(' · ')}
                              </div>
                            )}
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
                            <span className="u-text3-xs">
                              {rec.active_tickets ?? 0} tickets
                            </span>
                            <span style={{
                              fontSize: 'var(--text-sm)', fontWeight: 700, color: scoreColor,
                              background: `color-mix(in srgb, ${scoreColor} 15%, transparent)`,
                              border: `1px solid color-mix(in srgb, ${scoreColor} 30%, transparent)`,
                              borderRadius: 6, padding: '2px 9px',
                            }}>{score}%</span>
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
            <div style={{
              marginTop: 10, fontSize: 'var(--text-sm)', color: 'var(--danger)',
              background: 'color-mix(in srgb, var(--danger) 12%, transparent)',
              border: '1px solid color-mix(in srgb, var(--danger) 30%, transparent)',
              borderRadius: 8, padding: '8px 12px',
            }}>
              {(recommendMutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Error al obtener recomendación'}
            </div>
          )}
        </div>

        {/* Stats column */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <BarChart2 size={14} style={{ color: 'var(--purple)' }} />
            <span style={{ fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {t('sd.assign.load_by_agent', 'Carga por agente (tickets abiertos)')}
            </span>
          </div>

          {statsLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}><Spinner /></div>
          ) : !candidates.length ? (
            <EmptyState icon="📊" title={t('incidentassignment.sin_agentes_registrados')} />
          ) : (
            <div style={{
              background: 'var(--surface-3)',
              border: '1px solid var(--surface-4)',
              borderRadius: 10,
              padding: 12,
            }}>
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
            <div style={{
              marginTop: 10,
              fontSize: 'var(--text-xs)', color: 'var(--text-3)',
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              <span style={{
                fontWeight: 700, color: stats.total_unassigned > 0 ? 'var(--warning)' : 'var(--success)',
              }}>{stats.total_unassigned}</span>
              {t('sd.assign.unassigned', 'tickets sin asignar')}
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}
