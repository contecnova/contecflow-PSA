/**
 * useOfflineSync — estado de conexión y número de imputaciones en la cola
 * offline (`services/offlineQueue`).
 *
 * Auditoría 2026-11: antes leía de una segunda cola (Dexie, `offlineSync.ts`)
 * en la que nada escribía, así que el contador era siempre 0 aunque hubiera
 * imputaciones pendientes. La subida al reconectar la hace `initOfflineSync`
 * (main.tsx); aquí sólo se observa.
 *
 * Uso:
 *   const { isOnline, pendingCount, refresh } = useOfflineSync()
 */
import { useState, useEffect, useCallback } from 'react'
import { pendingCount as contarPendientes } from '../services/offlineQueue'

export default function useOfflineSync(intervaloMs = 3000) {
  const [isOnline, setIsOnline] = useState(() => navigator.onLine)
  const [pendingCount, setPendingCount] = useState(0)

  const refresh = useCallback(() => {
    contarPendientes()
      .then(n => setPendingCount(Number(n) || 0))
      .catch(() => {})
  }, [])

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

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, intervaloMs)
    return () => clearInterval(id)
  }, [isOnline, intervaloMs, refresh])

  return { isOnline, pendingCount, refresh }
}
