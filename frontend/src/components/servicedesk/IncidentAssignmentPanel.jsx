/**
 * IncidentAssignmentPanel.jsx — ML-powered incident assignment recommendations.
 * Connects to /api/v1/sd/incidents/{id}/assign/recommend and /sd/incidents/assign/stats
 */
import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import { UserCheck, BarChart2 } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

export default function IncidentAssignmentPanel() {
  const t = useAppT()
  const { dark, tokens } = useChartTheme()
  const [ticketId, setTicketId] = useState('')
  const [recommendations, setRecommendations] = useState(null)

  const { data: stats } = useQuery({
    queryKey: ['incident-assign-stats'],
    queryFn: () => api.get('/sd/incidents/assign/stats').then(r => r.data),
  })

  const recommendMutation = useMutation({
    mutationFn: (id) => api.post(`/sd/incidents/${id}/assign/recommend`).then(r => r.data),
    onSuccess: (data) => setRecommendations(data),
  })

  const cardCls = `rounded-xl border p-6 ${dark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`

  return (
    <div className={cardCls}>
      <div className="flex items-center gap-2 mb-4">
        <UserCheck className="w-5 h-5 text-blue-500" />
        <h2 className="text-lg font-bold">{t('sd.assign.title', 'Asignación Inteligente de Incidentes')}</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Recommendation input */}
        <div>
          <p className="text-sm font-medium mb-2">{t('sd.assign.get_recommendations', 'Obtener recomendaciones para ticket')}</p>
          <div className="flex gap-2 mb-4">
            <input
              type="text"
              placeholder="Ticket ID"
              value={ticketId}
              onChange={e => setTicketId(e.target.value)}
              className={`rounded border px-3 py-1.5 text-sm flex-1 ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
            />
            <button
              onClick={() => ticketId && recommendMutation.mutate(ticketId)}
              disabled={!ticketId || recommendMutation.isPending}
              className="px-4 py-1.5 rounded bg-blue-600 text-white text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {recommendMutation.isPending ? '...' : t('sd.assign.recommend', 'Recomendar')}
            </button>
          </div>

          {recommendations && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-gray-500 uppercase">{t('sd.assign.top_agents', 'Agentes sugeridos')}</p>
              {(recommendations.recommendations ?? []).map((rec, i) => (
                <div key={i} className={`flex items-center justify-between px-3 py-2 rounded-lg ${dark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                  <div>
                    <span className="font-medium text-sm">{rec.agent_name ?? rec.agent_id}</span>
                    {rec.reason && <p className="text-xs text-gray-400">{rec.reason}</p>}
                  </div>
                  <div className="flex items-center gap-3">
                    {rec.current_load != null && (
                      <span className="text-xs text-gray-400">{rec.current_load} tickets</span>
                    )}
                    <span className="text-sm font-semibold text-blue-500">{Math.round((rec.score ?? 0) * 100)}%</span>
                  </div>
                </div>
              ))}
              {recommendMutation.isError && (
                <p className="text-sm text-red-500">{t('sd.assign.error', 'Ticket no encontrado o error')}</p>
              )}
            </div>
          )}
        </div>

        {/* Stats */}
        {stats && (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <BarChart2 className="w-4 h-4 text-purple-500" />
              <p className="text-sm font-medium">{t('sd.assign.load_by_agent', 'Carga por agente')}</p>
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={stats.agent_loads ?? []}>
                <XAxis dataKey="agent_name" tick={{ fontSize: 10, fill: tokens.textColor }} />
                <YAxis tick={{ fontSize: 10, fill: tokens.textColor }} />
                <Tooltip
                  contentStyle={{ background: tokens.tooltipBg, border: 'none', borderRadius: 8 }}
                  labelStyle={{ color: tokens.textColor }}
                />
                <Bar dataKey="open_tickets" name="Tickets abiertos" fill="#60a5fa" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            {stats.total_unassigned != null && (
              <p className="text-xs text-gray-400 mt-1">
                {stats.total_unassigned} {t('sd.assign.unassigned', 'tickets sin asignar')}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
