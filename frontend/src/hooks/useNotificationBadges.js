import { useQuery } from '@tanstack/react-query'
import api, { alertsApi } from '../services/api'
import { useAuth } from '../context/AuthContext'

/**
 * Centralises the two badge queries (alert count + pending approvals)
 * that were previously living as local state inside Layout.
 * Any component can call this hook to read the same cached values
 * without triggering an extra network request.
 */
export default function useNotificationBadges() {
  const { hasRole } = useAuth()

  const { data: alerts } = useQuery({
    queryKey: ['alerts-count'],
    queryFn: () => alertsApi.list({ resolved: false }).then(r => r.data),
    refetchInterval: 60_000,
    enabled: hasRole('admin', 'pm', 'hr'),
  })

  const { data: pendingApprovals = [] } = useQuery({
    queryKey: ['approvals-pending-badge'],
    queryFn: () =>
      api.get('/approvals/requests/pending-my-action').then(r => r.data || []).catch(() => []),
    refetchInterval: 60_000,
  })

  const alertCount = alerts ? alerts.filter(a => !a.is_read).length : 0
  const approvalCount = pendingApprovals.length

  return { alertCount, approvalCount }
}
