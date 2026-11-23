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

interface BiSnapshotRow {
  key: string
  data: unknown
  stored_at: string
}

type BiDexie = Dexie & {
  kpi_snapshots: {
    put: (row: BiSnapshotRow) => Promise<unknown>
    get: (key: string) => Promise<BiSnapshotRow | undefined>
    where: (index: string) => { below: (value: string) => { delete: () => Promise<unknown> } }
  }
  project_snapshots: {
    put: (row: BiSnapshotRow) => Promise<unknown>
    get: (key: string) => Promise<BiSnapshotRow | undefined>
    where: (index: string) => { below: (value: string) => { delete: () => Promise<unknown> } }
  }
}

const db = new Dexie('contecflow_bi_offline') as BiDexie

db.version(1).stores({
  // key: composite string like "bi-kpis:30d:2026-04-28"
  kpi_snapshots:     'key, stored_at',
  project_snapshots: 'key, stored_at',
})

const TTL_MS = 8 * 60 * 60 * 1000 // 8 hours

/*
 * Auditoría 22-11-2026 (M2 del 05): la clave era constante ('kpis:mtd') y no se
 * borraba al cerrar sesión: sin conexión, otra persona del mismo navegador veía
 * los KPI financieros de la anterior. Ahora cada clave lleva `empresa:usuario`
 * (lo fija AuthContext con `establecerAmbitoBi`) y al salir se vacía la base.
 */
let _ambito: string | null = null

export function establecerAmbitoBi(userId: string | null, orgId: string | null): void {
  _ambito = userId ? `${orgId ?? '-'}:${userId}` : null
}

const clave = (tipo: string, periodKey: string) => (_ambito ? `${_ambito}:${tipo}:${periodKey}` : null)

/** Vacía la copia offline de BI (al cerrar sesión o caducar). */
export async function borrarCacheBi(): Promise<void> {
  try {
    await db.kpi_snapshots.where('stored_at').below('￿').delete()
    await db.project_snapshots.where('stored_at').below('￿').delete()
  } catch {
    // accesorio: IndexedDB no disponible
  }
}

function isExpired(storedAt?: string) {
  if (!storedAt) return true
  return Date.now() - new Date(storedAt).getTime() > TTL_MS
}

// ── KPI snapshots ─────────────────────────────────────────────────────────────

export async function cacheBiKpis(periodKey: string, data: unknown) {
  try {
    const k = clave('kpis', periodKey)
    if (!k) return
    await db.kpi_snapshots.put({ key: k, data, stored_at: new Date().toISOString() })
  } catch {
    // IndexedDB writes are best-effort; never break the app
  }
}

export async function getCachedBiKpis(periodKey: string) {
  try {
    const k = clave('kpis', periodKey)
    if (!k) return null
    const row = await db.kpi_snapshots.get(k)
    if (!row || isExpired(row.stored_at)) return null
    return row.data
  } catch {
    return null
  }
}

// ── Project health snapshots ──────────────────────────────────────────────────

export async function cacheBiProjects(periodKey: string, data: unknown) {
  try {
    const k = clave('projects', periodKey)
    if (!k) return
    await db.project_snapshots.put({ key: k, data, stored_at: new Date().toISOString() })
  } catch {
    // best-effort
  }
}

export async function getCachedBiProjects(periodKey: string) {
  try {
    const k = clave('projects', periodKey)
    if (!k) return null
    const row = await db.project_snapshots.get(k)
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
