/**
 * BiEtlPanel.jsx — BI ETL Connector management panel.
 * Connects to /api/v1/bi/etl/* endpoints.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import { RefreshCw, CheckCircle, AlertCircle, Clock } from 'lucide-react'

const STATUS_CONFIG = {
  connected: { icon: CheckCircle, cls: 'text-green-500' },
  disconnected: { icon: AlertCircle, cls: 'text-gray-400' },
  error: { icon: AlertCircle, cls: 'text-red-500' },
  syncing: { icon: Clock, cls: 'text-yellow-500' },
}

export default function BiEtlPanel() {
  const t = useAppT()
  const { dark } = useChartTheme()
  const qc = useQueryClient()
  const [syncingIds, setSyncingIds] = useState(new Set())

  const { data, isLoading } = useQuery({
    queryKey: ['bi-etl-connectors'],
    queryFn: () => api.get('/bi/etl/connectors').then(r => r.data),
    refetchInterval: 30_000,
  })

  const syncMutation = useMutation({
    mutationFn: (connectorId) => api.post(`/bi/etl/connectors/${connectorId}/sync`, {}).then(r => r.data),
    onMutate: (id) => setSyncingIds(s => new Set([...s, id])),
    onSettled: (_, __, id) => {
      setSyncingIds(s => { const next = new Set(s); next.delete(id); return next })
      qc.invalidateQueries({ queryKey: ['bi-etl-connectors'] })
    },
  })

  const cardCls = `rounded-xl border p-6 ${dark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`

  return (
    <div className={cardCls}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold">{t('bi.etl.title', 'Conectores ETL')}</h2>
        <button
          onClick={() => qc.invalidateQueries({ queryKey: ['bi-etl-connectors'] })}
          className="text-gray-400 hover:text-blue-500"
          title={t('bi.etl.refresh', 'Refrescar')}
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {isLoading ? (
        <div className="text-gray-400 text-sm">Loading…</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {(data?.connectors ?? []).map(c => {
            const StatusIcon = STATUS_CONFIG[c.status]?.icon ?? AlertCircle
            const statusCls = STATUS_CONFIG[c.status]?.cls ?? 'text-gray-400'
            const isSyncing = syncingIds.has(c.connector_id)
            return (
              <div
                key={c.connector_id}
                className={`rounded-lg border px-4 py-3 flex items-center justify-between ${dark ? 'bg-gray-800 border-gray-700' : 'bg-gray-50 border-gray-200'}`}
              >
                <div>
                  <div className="flex items-center gap-1.5">
                    <StatusIcon className={`w-4 h-4 ${statusCls}`} />
                    <span className="font-medium text-sm capitalize">{c.connector_id}</span>
                  </div>
                  {c.last_sync_at && (
                    <p className="text-xs text-gray-400 mt-0.5">
                      {new Date(c.last_sync_at).toLocaleString()} · {c.last_records} rec
                    </p>
                  )}
                </div>
                <button
                  onClick={() => syncMutation.mutate(c.connector_id)}
                  disabled={isSyncing}
                  className={`p-1.5 rounded-full hover:bg-blue-100 dark:hover:bg-blue-900 ${isSyncing ? 'opacity-50' : ''}`}
                  title={t('bi.etl.sync_now', 'Sincronizar ahora')}
                >
                  <RefreshCw className={`w-4 h-4 text-blue-500 ${isSyncing ? 'animate-spin' : ''}`} />
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
