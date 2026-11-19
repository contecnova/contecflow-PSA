import { useQuery } from '@tanstack/react-query'
// TODO type: services/api still JS.
import api, { alertsApi, mentionsApi } from '../services/api'
import { avisosApi } from '../services/api/avisos'
// TODO type: AuthContext still JSX/JS — useAuth typing inferred as any.
import { useAuth } from '../context/AuthContext'
import type { Mencion } from '../services/api/tipos-personas'
import { queryKeys } from '../constants/queryKeys'
import { POLL_DEFAULT_MS, STALE_SHORT_MS } from '../constants/timings'

export interface NotificationBadges {
  alertCount: number
  notifUnreadCount: number
  approvalCount: number
  mentionCount: number
  inboxTotal: number
}

/**
 * Centralises badge queries (alerts + approvals + mentions) y
 * los unifica en un total para el inbox bell del header.
 * notifUnreadCount es exclusivo para el badge de la pestaña Notificaciones del Inbox.
 */
export default function useNotificationBadges(): NotificationBadges {
  const { puede, user, loading } = useAuth()
  const canQueryProtected = !loading && !!user

  const { data: alerts } = useQuery({
    // TODO #82: migrate to queryKeys — alerts count badge has a dedicated key not in factory
    queryKey: ['alerts-count'],
    queryFn: () => alertsApi.list({ resolved: false }).then(r => r.data),
    refetchInterval: POLL_DEFAULT_MS,
    staleTime: STALE_SHORT_MS,
    enabled: puede('alertas.ver'),
  })

  // Misma clave y misma consulta que la campana de la barra superior
  // (16-11-2026): un COUNT en `/unread-count`, una sola petición para las dos.
  const { data: notifUnread = 0 } = useQuery<number>({
    queryKey: queryKeys.notifications.badges(),
    queryFn: () => avisosApi.contador().catch(() => 0),
    refetchInterval: POLL_DEFAULT_MS,
    staleTime: STALE_SHORT_MS,
    enabled: canQueryProtected,
  })

  const { data: pendingApprovals = [] } = useQuery<unknown[]>({
    queryKey: queryKeys.approvals.pending(),
    queryFn: () =>
      api.get('/approvals/requests/pending-my-action').then((r: { data: unknown[] }) => r.data || []).catch(() => [] as unknown[]),
    refetchInterval: POLL_DEFAULT_MS,
    staleTime: STALE_SHORT_MS,
    enabled: canQueryProtected,
  })

  const { data: mentions = [] } = useQuery<Mencion[]>({
    // TODO #82: migrate to queryKeys — mentions not yet defined in factory
    queryKey: ['mentions-unread'],
    queryFn: () =>
      mentionsApi.mentions(true).then((r) => r.data).catch(() => [] as Mencion[]),
    refetchInterval: POLL_DEFAULT_MS,
    staleTime: STALE_SHORT_MS,
    enabled: canQueryProtected,
  })

  const alertCount = alerts ? alerts.filter(a => !a.is_read).length : 0
  const notifUnreadCount = Number(notifUnread || 0)
  const approvalCount = pendingApprovals.length
  const mentionCount = mentions.length
  const inboxTotal = alertCount + approvalCount + mentionCount

  return { alertCount, notifUnreadCount, approvalCount, mentionCount, inboxTotal }
}

// Named export to support `import { useNotificationBadges } from '../hooks'`
export { useNotificationBadges }
