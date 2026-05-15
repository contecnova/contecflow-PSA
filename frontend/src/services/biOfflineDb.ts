/**
 * biOfflineDb.js — Dexie (IndexedDB) offline cache for BI dashboard data.
 *
 * Stores the last known BI KPI snapshot and project health data so the
 * dashboard stays functional when the user is offline.
 *
 * Usage:
 *   import { cacheBiKpis, getCachedBiKpis, cacheBiProjects, getCachedBiProjects } from './biOfflineDb'
 */
import Dexie from 'dexie'

const db = new Dexie('contecflow_bi_offline')

db.version(1).stores({
  // key: composite string like "bi-kpis:30d:2026-04-28"
  kpi_snapshots:     'key, stored_at',
  project_snapshots: 'key, stored_at',
})

const TTL_MS = 8 * 60 * 60 * 1000 // 8 hours

function isExpired(storedAt) {
  if (!storedAt) return true
  return Date.now() - new Date(storedAt).getTime() > TTL_MS
}

// ── KPI snapshots ─────────────────────────────────────────────────────────────

export async function cacheBiKpis(periodKey, data) {
  try {
    await db.kpi_snapshots.put({ key: `kpis:${periodKey}`, data, stored_at: new Date().toISOString() })
  } catch {
    // IndexedDB writes are best-effort; never break the app
  }
}

export async function getCachedBiKpis(periodKey) {
  try {
    const row = await db.kpi_snapshots.get(`kpis:${periodKey}`)
    if (!row || isExpired(row.stored_at)) return null
    return row.data
  } catch {
    return null
  }
}

// ── Project health snapshots ──────────────────────────────────────────────────

export async function cacheBiProjects(periodKey, data) {
  try {
    await db.project_snapshots.put({ key: `projects:${periodKey}`, data, stored_at: new Date().toISOString() })
  } catch {
    // best-effort
  }
}

export async function getCachedBiProjects(periodKey) {
  try {
    const row = await db.project_snapshots.get(`projects:${periodKey}`)
    if (!row || isExpired(row.stored_at)) return null
    return row.data
  } catch {
    return null
  }
}

// ── Purge expired entries (call on app init) ──────────────────────────────────

export async function purgeExpiredBiCache() {
  const cutoff = new Date(Date.now() - TTL_MS).toISOString()
  try {
    await db.kpi_snapshots.where('stored_at').below(cutoff).delete()
    await db.project_snapshots.where('stored_at').below(cutoff).delete()
  } catch {
    // best-effort
  }
}

export default db
