import { useQuery } from '@tanstack/react-query'
// TODO type: services/api still JS.
import api, { alertsApi, mentionsApi } from '../services/api'
// TODO type: AuthContext still JSX/JS — useAuth typing inferred as any.
import { useAuth } from '../context/AuthContext'
import { queryKeys } from '../constants/queryKeys'
import { POLL_DEFAULT_MS, STALE_SHORT_MS } from '../constants/timings'
import { COUNT_ONLY_PAGE_SIZE } from '../constants/pagination'

interface AlertItem {
  id?: string
  is_read?: boolean
  [extra: string]: unknown
}

interface NotificationsData {
  unread_count?: number
  [extra: string]: unknown
}

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
  const { hasRole, user, loading } = useAuth() as {
    hasRole: (...roles: string[]) => boolean
    user: unknown
    loading: boolean
  }
  const canQueryProtected = !loading && !!user

  const { data: alerts } = useQuery<AlertItem[]>({
    // TODO #82: migrate to queryKeys — alerts count badge has a dedicated key not in factory
    queryKey: ['alerts-count'],
    queryFn: () => alertsApi.list({ resolved: false }).then((r: { data?: { items?: AlertItem[] } | AlertItem[] | null }) => {
      const d = r?.data
      if (Array.isArray(d)) return d
      return d?.items ?? []
    }),
    refetchInterval: POLL_DEFAULT_MS,
    staleTime: STALE_SHORT_MS,
    enabled: hasRole('admin', 'pm', 'hr'),
  })

  const { data: notificationsData } = useQuery<NotificationsData>({
    queryKey: queryKeys.notifications.badges(),
    queryFn: () =>
      api.get('/enterprise/notifications', { params: { page_size: COUNT_ONLY_PAGE_SIZE } })
        .then((r: { data: NotificationsData }) => r.data || { unread_count: 0 })
        .catch(() => ({ unread_count: 0 } as NotificationsData)),
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

  const { data: mentions = [] } = useQuery<unknown[]>({
    // TODO #82: migrate to queryKeys — mentions not yet defined in factory
    queryKey: ['mentions-unread'],
    queryFn: () =>
      mentionsApi.mentions(true).then((r: { data: unknown[] }) => r.data || []).catch(() => [] as unknown[]),
    refetchInterval: POLL_DEFAULT_MS,
    staleTime: STALE_SHORT_MS,
    enabled: canQueryProtected,
  })

  const alertCount = alerts ? alerts.filter((a: AlertItem) => !a.is_read).length : 0
  const notifUnreadCount = Number(notificationsData?.unread_count || 0)
  const approvalCount = pendingApprovals.length
  const mentionCount = Array.isArray(mentions) ? mentions.length : 0
  const inboxTotal = alertCount + approvalCount + mentionCount

  return { alertCount, notifUnreadCount, approvalCount, mentionCount, inboxTotal }
}

// Named export to support `import { useNotificationBadges } from '../hooks'`
export { useNotificationBadges }
