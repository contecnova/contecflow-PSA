import { useQuery } from '@tanstack/react-query'
import api, { alertsApi, mentionsApi } from '../services/api'
import { useAuth } from '../context/AuthContext'

/**
 * Centralises badge queries (alerts + approvals + mentions) y
 * los unifica en un total para el inbox bell del header.
 * notifUnreadCount es exclusivo para el badge de la pestaña Notificaciones del Inbox.
 */
export default function useNotificationBadges() {
  const { hasRole, user, loading } = useAuth()
  const canQueryProtected = !loading && !!user

  const { data: alerts } = useQuery({
    queryKey: ['alerts-count'],
    queryFn: () => alertsApi.list({ resolved: false }).then(r => r.data?.items ?? r.data ?? []),
    refetchInterval: 60_000,
    staleTime: 30 * 1000,
    enabled: hasRole('admin', 'pm', 'hr'),
  })

  const { data: notificationsData } = useQuery({
    queryKey: ['notifications-unread-badge'],
    queryFn: () =>
      api.get('/enterprise/notifications', { params: { page_size: 1 } })
        .then(r => r.data || { unread_count: 0 })
        .catch(() => ({ unread_count: 0 })),
    refetchInterval: 60_000,
    staleTime: 30 * 1000,
    enabled: canQueryProtected,
  })

  const { data: pendingApprovals = [] } = useQuery({
    queryKey: ['approvals-pending-badge'],
    queryFn: () =>
      api.get('/approvals/requests/pending-my-action').then(r => r.data || []).catch(() => []),
    refetchInterval: 60_000,
    staleTime: 30 * 1000,
    enabled: canQueryProtected,
  })

  const { data: mentions = [] } = useQuery({
    queryKey: ['mentions-unread'],
    queryFn: () =>
      mentionsApi.mentions(true).then(r => r.data || []).catch(() => []),
    refetchInterval: 60_000,
    staleTime: 30 * 1000,
    enabled: canQueryProtected,
  })

  const alertCount = alerts ? alerts.filter(a => !a.is_read).length : 0
  const notifUnreadCount = Number(notificationsData?.unread_count || 0)
  const approvalCount = pendingApprovals.length
  const mentionCount = Array.isArray(mentions) ? mentions.length : 0
  const inboxTotal = alertCount + approvalCount + mentionCount

  return { alertCount, notifUnreadCount, approvalCount, mentionCount, inboxTotal }
}
