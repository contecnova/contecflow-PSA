// Auditoría 05 (C.2, H4), 23-11-2026: la cola offline de imputaciones es de su
// dueño (persona y empresa): otra sesión en el mismo puesto no la ve ni la envía.
import 'fake-indexeddb/auto'
import { describe, it, expect } from 'vitest'
import { establecerDuenoDeLaCola, queueImputation, pendingCount, syncPending } from '../../services/offlineQueue'

describe('cola offline por usuario', () => {
  it('cada dueño ve y sincroniza solo lo suyo', async () => {
    establecerDuenoDeLaCola({ user_id: 'u1', org_id: 'o1' })
    await queueImputation({ hours: 1 })
    expect(await pendingCount()).toBe(1)

    establecerDuenoDeLaCola({ user_id: 'u2', org_id: 'o1' })
    expect(await pendingCount()).toBe(0)
    const enviadas: unknown[] = []
    await syncPending({ post: async (_u: string, p: Record<string, unknown>) => { enviadas.push(p) } })
    expect(enviadas).toHaveLength(0)

    establecerDuenoDeLaCola({ user_id: 'u1', org_id: 'o1' })
    await syncPending({ post: async (_u: string, p: Record<string, unknown>) => { enviadas.push(p) } })
    expect(enviadas).toHaveLength(1)
  })
})
