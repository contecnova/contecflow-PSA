/**
 * offlineSync.js — Dexie-based offline data sync for PWA support.
 * 
 * Uses Dexie (IndexedDB wrapper) to cache critical data locally.
 * When online, syncs pending operations to the backend.
 * 
 * Usage:
 *   import { offlineDb, queueOperation, syncPendingOps } from './offlineSync'
 *   
 *   // Cache data for offline reading
 *   await offlineDb.cache.put({ key: 'projects', data: [...], ts: Date.now() })
 *   
 *   // Queue a write operation when offline
 *   await queueOperation({ method: 'POST', url: '/projects', body: {...} })
 *   
 *   // Sync when back online
 *   navigator.addEventListener('online', syncPendingOps)
 */

let Dexie
let _DEXIE_AVAILABLE = false

try {
  Dexie = (await import('dexie')).default
  _DEXIE_AVAILABLE = true
} catch {
  console.warn('[offlineSync] Dexie not available — offline sync disabled')
}

class OfflineDb {
  constructor() {
    if (!_DEXIE_AVAILABLE) {
      this._db = null
      return
    }
    this._db = new Dexie('contecflow_offline')
    this._db.version(1).stores({
      cache: 'key, ts',           // cached API responses: { key, data, ts }
      pendingOps: '++id, ts',     // queued mutations: { method, url, body, ts, retries }
      userPrefs: 'key',           // local user preferences: { key, value }
    })
  }

  get cache() { return this._db?.cache ?? _noop_table() }
  get pendingOps() { return this._db?.pendingOps ?? _noop_table() }
  get userPrefs() { return this._db?.userPrefs ?? _noop_table() }

  get isAvailable() { return _DEXIE_AVAILABLE && this._db != null }
}

function _noop_table() {
  // No-op table when Dexie not available
  return {
    put: async () => null,
    get: async () => null,
    getAll: async () => [],
    delete: async () => null,
    where: () => ({ toArray: async () => [], delete: async () => null }),
  }
}

export const offlineDb = new OfflineDb()

/**
 * Queue a mutating API operation for deferred execution when back online.
 * @param {{ method: string, url: string, body?: object, headers?: object }} op
 */
export async function queueOperation(op) {
  await offlineDb.pendingOps.put({
    ...op,
    ts: Date.now(),
    retries: 0,
  })
}

/**
 * Persist API response to local cache.
 * @param {string} key
 * @param {any} data
 * @param {number} [ttlMs=5 * 60 * 1000] TTL in milliseconds
 */
export async function cacheResponse(key, data, ttlMs = 5 * 60 * 1000) {
  await offlineDb.cache.put({ key, data, ts: Date.now(), expiresAt: Date.now() + ttlMs })
}

/**
 * Read cached API response. Returns null if expired or not found.
 * @param {string} key
 */
export async function readCache(key) {
  const entry = await offlineDb.cache.get(key)
  if (!entry) return null
  if (entry.expiresAt && Date.now() > entry.expiresAt) {
    await offlineDb.cache.delete(key)
    return null
  }
  return entry.data
}

/**
 * Sync all pending queued operations to the backend.
 * Safe to call multiple times — idempotent on empty queue.
 * @param {function} apiFn — async function(op) => response (default: fetch)
 */
export async function syncPendingOps(apiFn) {
  if (!navigator.onLine) return { synced: 0, failed: 0 }
  
  const ops = await offlineDb.pendingOps.getAll()
  let synced = 0
  let failed = 0

  for (const op of ops) {
    try {
      if (apiFn) {
        await apiFn(op)
      } else {
        await fetch(op.url, {
          method: op.method,
          headers: { 'Content-Type': 'application/json', ...(op.headers ?? {}) },
          body: op.body ? JSON.stringify(op.body) : undefined,
        })
      }
      await offlineDb.pendingOps.delete(op.id)
      synced++
    } catch {
      failed++
      // Increment retry count; give up after 5
      if (op.retries >= 5) {
        await offlineDb.pendingOps.delete(op.id)
      } else {
        await offlineDb.pendingOps.put({ ...op, retries: (op.retries ?? 0) + 1 })
      }
    }
  }

  return { synced, failed, total: ops.length }
}

/**
 * React hook for offline status + auto-sync on reconnect.
 * 
 * @example
 * import { useOfflineSync } from './offlineSync'
 * const { isOnline, pendingCount } = useOfflineSync(apiInstance)
 */
export function useOfflineSync(apiInstance) {
  const { useState, useEffect } = require('react')
  const [isOnline, setIsOnline] = useState(() => navigator.onLine)
  const [pendingCount, setPendingCount] = useState(0)
  const [lastSyncResult, setLastSyncResult] = useState(null)

  useEffect(() => {
    const updateOnline = () => setIsOnline(true)
    const updateOffline = () => setIsOnline(false)
    window.addEventListener('online', updateOnline)
    window.addEventListener('offline', updateOffline)
    return () => {
      window.removeEventListener('online', updateOnline)
      window.removeEventListener('offline', updateOffline)
    }
  }, [])

  useEffect(() => {
    offlineDb.pendingOps.getAll().then(ops => setPendingCount(ops.length)).catch(() => {})
  }, [isOnline])

  useEffect(() => {
    if (!isOnline) return
    const apiFn = apiInstance
      ? (op) => apiInstance.request({ method: op.method, url: op.url, data: op.body })
      : undefined
    syncPendingOps(apiFn)
      .then(result => {
        setLastSyncResult(result)
        setPendingCount(0)
      })
      .catch(() => {})
  }, [isOnline, apiInstance])

  return { isOnline, pendingCount, lastSyncResult }
}
