/**
 * useOfflineSync — React hook for offline status + auto-sync on reconnect.
 * Wraps the Dexie-based offlineSync service with proper ESM React imports.
 *
 * Usage:
 *   import useOfflineSync from './hooks/useOfflineSync'
 *   const { isOnline, pendingCount, lastSyncResult } = useOfflineSync()
 */
import { useState, useEffect } from 'react'
import { syncPendingOps, offlineDb } from '../services/offlineSync'
import api from '../services/api'

export default function useOfflineSync() {
  const [isOnline, setIsOnline] = useState(() => navigator.onLine)
  const [pendingCount, setPendingCount] = useState(0)
  const [lastSyncResult, setLastSyncResult] = useState(null)

  useEffect(() => {
    const goOnline  = () => setIsOnline(true)
    const goOffline = () => setIsOnline(false)
    window.addEventListener('online',  goOnline)
    window.addEventListener('offline', goOffline)
    return () => {
      window.removeEventListener('online',  goOnline)
      window.removeEventListener('offline', goOffline)
    }
  }, [])

  // Update pending count whenever connectivity changes
  useEffect(() => {
    offlineDb.pendingOps.toArray()
      .then(ops => setPendingCount(ops.length))
      .catch(() => {})
  }, [isOnline])

  // Auto-sync on reconnect
  useEffect(() => {
    if (!isOnline) return
    const apiFn = (op) =>
      api.request({ method: op.method, url: op.url, data: op.body, headers: op.headers })
    syncPendingOps(apiFn)
      .then(result => {
        setLastSyncResult(result)
        setPendingCount(0)
      })
      .catch(() => {})
  }, [isOnline])

  return { isOnline, pendingCount, lastSyncResult }
}
