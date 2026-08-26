/**
 * offlineSync.test.js — Tests for Dexie offline sync with conflict resolution
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  offlineDb,
  queueOperation,
  syncPendingOps,
  cacheResponse,
  readCache,
  resolveConflict,
  getPendingConflicts,
  getConflictHistory,
  getSyncStats,
  clearAllOfflineData,
  setSyncConflictStrategy,
  subscribeToSyncEvents,
} from '../../src/services/offlineSync'

describe('Dexie Offline Sync', () => {
  beforeEach(async () => {
    // Clear all data before each test
    await clearAllOfflineData()
  })

  afterEach(async () => {
    await clearAllOfflineData()
  })

  describe('Queue Operations', () => {
    it('should queue an operation with default priority', async () => {
      await queueOperation({
        method: 'POST',
        url: '/api/projects',
        body: { name: 'Test Project' },
      })

      const ops = await offlineDb.pendingOps.toArray()
      expect(ops.length).toBe(1)
      expect(ops[0].url).toBe('/api/projects')
      expect(ops[0].priority).toBe(1) // 'normal'
      expect(ops[0].body.name).toBe('Test Project')
    })

    it('should queue operations with different priorities', async () => {
      await queueOperation({
        method: 'POST',
        url: '/api/critical',
        body: {},
        priority: 'critical',
      })

      await queueOperation({
        method: 'POST',
        url: '/api/low',
        body: {},
        priority: 'low',
      })

      const ops = await offlineDb.pendingOps.orderBy('priority').toArray()
      expect(ops[0].url).toBe('/api/critical')
      expect(ops[0].priority).toBe(0) // critical
      expect(ops[1].url).toBe('/api/low')
      expect(ops[1].priority).toBe(2) // low
    })

    it('should generate idempotency keys', async () => {
      const op1 = {
        method: 'POST',
        url: '/api/test',
        body: { data: 'test' },
      }

      await queueOperation(op1)
      await queueOperation(op1)

      const ops = await offlineDb.pendingOps.toArray()
      expect(ops.length).toBe(2)
      expect(ops[0].idempotencyKey).toBeDefined()
      expect(ops[1].idempotencyKey).toBeDefined()
      expect(ops[0].idempotencyKey).not.toBe(ops[1].idempotencyKey)
    })
  })

  describe('Cache Operations', () => {
    it('should cache and retrieve responses', async () => {
      const data = { id: 1, name: 'Project' }
      await cacheResponse('projects', data)

      const cached = await readCache('projects')
      expect(cached).toEqual(data)
    })

    it('should handle expired cache entries', async () => {
      const data = { id: 1 }
      await cacheResponse('test', data, 100) // 100ms TTL

      // Should be available immediately
      let cached = await readCache('test')
      expect(cached).toEqual(data)

      // Wait for expiration
      await new Promise(resolve => setTimeout(resolve, 150))
      cached = await readCache('test')
      expect(cached).toBeNull()
    })
  })

  describe('Conflict Resolution', () => {
    it('should detect 409 conflicts', async () => {
      const mockApiFn = vi.fn(async (_op) => ({
        status: 409,
        json: async () => ({ serverValue: 'conflict' }),
      }))

      await queueOperation({
        method: 'PUT',
        url: '/api/resource/1',
        body: { value: 'local' },
        conflictStrategy: 'server-wins',
      })

      const result = await syncPendingOps(mockApiFn)
      expect(result.conflicts).toBe(1)
    })

    it('should handle server-wins conflict strategy', async () => {
      const mockApiFn = vi.fn(async (_op) => ({
        status: 409,
        json: async () => ({ value: 'server' }),
      }))

      setSyncConflictStrategy('server-wins')

      await queueOperation({
        method: 'PUT',
        url: '/api/resource/1',
        body: { value: 'local' },
        conflictStrategy: 'server-wins',
      })

      const result = await syncPendingOps(mockApiFn)
      expect(result.conflicts).toBe(1)

      // Op should be removed (server wins)
      const pendingOps = await offlineDb.pendingOps.toArray()
      expect(pendingOps.length).toBe(0)
    })

    it('should handle manual conflict strategy', async () => {
      const mockApiFn = vi.fn(async (_op) => ({
        status: 409,
        json: async () => ({ value: 'server' }),
      }))

      await queueOperation({
        method: 'PUT',
        url: '/api/resource/1',
        body: { value: 'local' },
        conflictStrategy: 'manual',
      })

      const result = await syncPendingOps(mockApiFn)
      expect(result.conflicts).toBe(1)

      // Op should remain for manual review
      const pendingOps = await offlineDb.pendingOps.toArray()
      expect(pendingOps.length).toBe(1)

      // Conflict should be logged
      const conflicts = await getPendingConflicts()
      expect(conflicts.length).toBe(1)
    })

    it('should resolve conflicts manually', async () => {
      const mockApiFn = vi.fn(async (_op) => ({
        status: 409,
        json: async () => ({ value: 'server' }),
      }))

      await queueOperation({
        method: 'PUT',
        url: '/api/resource/1',
        body: { value: 'local' },
        conflictStrategy: 'manual',
      })

      await syncPendingOps(mockApiFn)
      const conflicts = await getPendingConflicts()
      expect(conflicts.length).toBe(1)

      // Resolve with server version
      await resolveConflict({
        conflictId: conflicts[0].id,
        resolution: 'server',
      })

      const resolved = await getPendingConflicts()
      expect(resolved.length).toBe(0)

      const history = await getConflictHistory()
      expect(history.length).toBe(1)
      expect(history[0].resolution).toBe('server')
    })
  })

  describe('Sync with Exponential Backoff', () => {
    it('should retry failed operations', async () => {
      let callCount = 0
      const mockApiFn = vi.fn(async (_op) => {
        callCount++
        if (callCount < 3) {
          throw new Error('Network error')
        }
        return { status: 200 }
      })

      await queueOperation({
        method: 'POST',
        url: '/api/test',
        body: { data: 'test' },
      })

      const result = await syncPendingOps(mockApiFn)
      expect(result.failed).toBe(1)
      expect(result.synced).toBe(0)

      // Op should be marked for retry
      const ops = await offlineDb.pendingOps.toArray()
      expect(ops[0].retries).toBe(1)
    })

    it('should give up after max retries', async () => {
      const mockApiFn = vi.fn(async (_op) => {
        throw new Error('Network error')
      })

      await queueOperation({
        method: 'POST',
        url: '/api/test',
        body: { data: 'test' },
      })

      // Simulate 5 retries
      for (let i = 0; i < 5; i++) {
        const ops = await offlineDb.pendingOps.toArray()
        if (ops.length === 0) break
        await syncPendingOps(mockApiFn)
      }

      const final = await offlineDb.pendingOps.toArray()
      expect(final.length).toBe(0)
    })
  })

  describe('Sync Events', () => {
    it('should emit sync events', async () => {
      const events = []
      const unsub = subscribeToSyncEvents((event) => {
        events.push(event)
      })

      const mockApiFn = vi.fn(async (_op) => ({ status: 200 }))

      await queueOperation({
        method: 'POST',
        url: '/api/test',
        body: {},
      })

      await syncPendingOps(mockApiFn)

      // Should have events: sync_start, sync_progress, sync_complete
      expect(events.length).toBeGreaterThan(0)
      expect(events.some(e => e.type === 'sync_start')).toBe(true)
      expect(events.some(e => e.type === 'sync_complete')).toBe(true)

      unsub()
    })
  })

  describe('Sync Statistics', () => {
    it('should return sync stats', async () => {
      await queueOperation({
        method: 'POST',
        url: '/api/test1',
        body: {},
      })

      await queueOperation({
        method: 'POST',
        url: '/api/test2',
        body: {},
      })

      const stats = await getSyncStats()
      expect(stats.pendingOpsCount).toBe(2)
      expect(stats.pendingConflictsCount).toBe(0)
    })

    it('should track resolved conflicts', async () => {
      const mockApiFn = vi.fn(async (_op) => ({
        status: 409,
        json: async () => ({}),
      }))

      await queueOperation({
        method: 'PUT',
        url: '/api/test',
        body: {},
        conflictStrategy: 'manual',
      })

      await syncPendingOps(mockApiFn)

      const conflicts = await getPendingConflicts()
      await resolveConflict({
        conflictId: conflicts[0].id,
        resolution: 'server',
      })

      const stats = await getSyncStats()
      expect(stats.resolvedConflictsCount).toBe(1)
    })
  })

  describe('Edge Cases', () => {
    it('should handle empty sync queue', async () => {
      const result = await syncPendingOps()
      expect(result.synced).toBe(0)
      expect(result.failed).toBe(0)
      expect(result.conflicts).toBe(0)
      expect(result.total).toBe(0)
    })

    it('should clear all offline data', async () => {
      await queueOperation({
        method: 'POST',
        url: '/api/test',
        body: {},
      })

      await cacheResponse('key', { data: 'test' })

      await clearAllOfflineData()

      const ops = await offlineDb.pendingOps.toArray()
      const cached = await readCache('key')

      expect(ops.length).toBe(0)
      expect(cached).toBeNull()
    })
  })
})
