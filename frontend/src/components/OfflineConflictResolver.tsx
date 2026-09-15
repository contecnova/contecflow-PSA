/**
 * OfflineConflictResolver — UI for managing offline sync conflicts
 * 
 * Displays pending conflicts and allows users to choose resolution strategy:
 * - Accept server version
 * - Keep local version
 * - Manual merge
 */

import { useState, useEffect } from 'react'
import {
  getPendingConflicts,
  resolveConflict,
  getConflictHistory,
} from '../services/offlineSync'
import { useAppT } from '../i18n/AppLangContext'

type ConflictItem = {
  id?: number
  opId: string
  localValue: unknown
  serverValue: unknown
  strategy: string
  resolvedAt: number | null
  resolution: 'local' | 'server' | 'merged' | null
}

export default function OfflineConflictResolver() {
  const t = useAppT()
  const [conflicts, setConflicts] = useState<ConflictItem[]>([])
  const [selectedConflict, setSelectedConflict] = useState<ConflictItem | null>(null)
  const [resolving, setResolving] = useState(false)
  const [history, setHistory] = useState<ConflictItem[]>([])
  const [showHistory, setShowHistory] = useState(false)

  // Load conflicts on mount
  useEffect(() => {
    refreshConflicts()
    const interval = setInterval(refreshConflicts, 5000)
    return () => clearInterval(interval)
  }, [])

  async function refreshConflicts() {
    try {
      const pending = await getPendingConflicts()
      setConflicts(pending)
      if (pending.length === 0) {
        setSelectedConflict(null)
      }
    } catch (e) {
      console.error('[ConflictResolver] Error loading conflicts:', e)
    }
  }

  async function loadHistory() {
    try {
      const h = await getConflictHistory(20)
      setHistory(h)
    } catch (e) {
      console.error('[ConflictResolver] Error loading history:', e)
    }
  }

  async function handleResolve(conflict: ConflictItem, strategy: 'local' | 'server' | 'merged') {
    setResolving(true)
    try {
      await resolveConflict({
        conflictId: conflict.id!,
        resolution: strategy,
      })
      await refreshConflicts()
      setSelectedConflict(null)
    } catch (e) {
      console.error('[ConflictResolver] Error resolving:', e)
    } finally {
      setResolving(false)
    }
  }

  function handleShowHistory() {
    if (!showHistory) {
      loadHistory()
    }
    setShowHistory(!showHistory)
  }

  if (conflicts.length === 0 && !showHistory) {
    return null
  }

  return (
    <div
      role="region"
      aria-label={showHistory ? t('offline_conflicts.aria_history') : t('offline_conflicts.aria_conflicts')}
      style={{
        position: 'fixed',
        bottom: 20,
        right: 20,
        width: '400px',
        maxHeight: '500px',
        background: 'var(--surface-2)',
        border: '1px solid var(--text-2)',
        borderRadius: 8,
        boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
        zIndex: 9001,
        overflow: 'auto',
        fontFamily: 'system-ui, sans-serif',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '12px 16px',
          background: 'var(--surface-1)',
          borderBottom: '1px solid var(--surface-5)',
          position: 'sticky',
          top: 0,
        }}
      >
        <span style={{ fontSize: "var(--text-md)", fontWeight: 600, color: 'var(--text-1)' }}>
          {showHistory ? t('offline_conflicts.title_history') : t('offline_conflicts.title_count', { count: conflicts.length })}
        </span>
        <button
          onClick={handleShowHistory}
          style={{
            background: 'transparent',
            border: '1px solid var(--surface-4)',
            borderRadius: 4,
            color: 'var(--text-3)',
            fontSize: "var(--text-sm)",
            padding: '4px 8px',
            cursor: 'pointer',
          }}
        >
          {showHistory ? t('offline_conflicts.btn_pending') : t('offline_conflicts.btn_history')}
        </button>
      </div>

      {/* History View */}
      {showHistory && (
        <div style={{ padding: 12 }}>
          {history.length === 0 ? (
            <p style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', margin: 0 }}>{t('offline_conflicts.no_history')}</p>
          ) : (
            history.map((item) => (
              <div
                key={item.id}
                style={{
                  padding: 8,
                  marginBottom: 8,
                  background: 'var(--surface-5)',
                  borderRadius: 4,
                  fontSize: "var(--text-xs)",
                  color: 'var(--text-2)',
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: 4 }}>
                  {t('offline_conflicts.conflict_num', { id: item.id })}
                </div>
                <div>{t('offline_conflicts.operation', { opId: item.opId })}</div>
                <div>{t('offline_conflicts.resolution', { resolution: item.resolution })}</div>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', marginTop: 4 }}>
                  {item.resolvedAt == null ? '—' : new Date(item.resolvedAt).toLocaleTimeString()}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Conflicts View */}
      {!showHistory && (
        <div style={{ padding: 12 }}>
          {selectedConflict ? (
            <div>
              <button
                onClick={() => setSelectedConflict(null)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--accent)',
                  cursor: 'pointer',
                  fontSize: "var(--text-sm)",
                  marginBottom: 12,
                  padding: 0,
                }}
              >
                {t('offline_conflicts.back_to_list')}
              </button>

              <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)', marginBottom: 8 }}>
                  {t('offline_conflicts.conflict_num', { id: selectedConflict.id })}
                </div>

                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 8 }}>
                  {t('offline_conflicts.operation', { opId: selectedConflict.opId })}
                </div>

                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: "var(--text-xs)", fontWeight: 500, color: 'var(--text-1)', marginBottom: 4 }}>
                    {t('offline_conflicts.local_value')}
                  </div>
                  <pre
                    style={{
                      background: 'var(--surface-2)',
                      border: '1px solid var(--surface-5)',
                      borderRadius: 4,
                      padding: 8,
                      fontSize: "var(--text-2xs)",
                      color: 'var(--text-2)',
                      margin: 0,
                      overflow: 'auto',
                      maxHeight: 100,
                    }}
                  >
                    {JSON.stringify(selectedConflict.localValue, null, 2)}
                  </pre>
                </div>

                <div>
                  <div style={{ fontSize: "var(--text-xs)", fontWeight: 500, color: 'var(--text-1)', marginBottom: 4 }}>
                    {t('offline_conflicts.server_value')}
                  </div>
                  <pre
                    style={{
                      background: 'var(--surface-2)',
                      border: '1px solid var(--surface-5)',
                      borderRadius: 4,
                      padding: 8,
                      fontSize: "var(--text-2xs)",
                      color: 'var(--text-2)',
                      margin: 0,
                      overflow: 'auto',
                      maxHeight: 100,
                    }}
                  >
                    {JSON.stringify(selectedConflict.serverValue, null, 2)}
                  </pre>
                </div>
              </div>

              {/* Resolution buttons */}
              <div style={{ display: 'flex', gap: 8, justifyContent: 'space-between' }}>
                <button
                  onClick={() => handleResolve(selectedConflict, 'server')}
                  disabled={resolving}
                  style={{
                    flex: 1,
                    padding: '6px 12px',
                    background: 'var(--success)',
                    border: 'none',
                    borderRadius: 4,
                    color: '#fff',
                    fontSize: "var(--text-xs)",
                    fontWeight: 500,
                    cursor: resolving ? 'wait' : 'pointer',
                    opacity: resolving ? 0.6 : 1,
                  }}
                >
                  {resolving ? t('offline_conflicts.resolving') : t('offline_conflicts.accept_server')}
                </button>
                <button
                  onClick={() => handleResolve(selectedConflict, 'local')}
                  disabled={resolving}
                  style={{
                    flex: 1,
                    padding: '6px 12px',
                    background: 'var(--danger)',
                    border: 'none',
                    borderRadius: 4,
                    color: '#fff',
                    fontSize: "var(--text-xs)",
                    fontWeight: 500,
                    cursor: resolving ? 'wait' : 'pointer',
                    opacity: resolving ? 0.6 : 1,
                  }}
                >
                  {resolving ? t('offline_conflicts.resolving') : t('offline_conflicts.keep_local')}
                </button>
              </div>
            </div>
          ) : (
            /* Conflict List */
            <div>
              {conflicts.map((conflict) => (
                <button
                  key={conflict.id}
                  onClick={() => setSelectedConflict(conflict)}
                  type="button"
                  style={{
                    padding: 10,
                    marginBottom: 8,
                    background: 'var(--surface-5)',
                    borderRadius: 4,
                    cursor: 'pointer',
                    border: '1px solid var(--surface-4)',
                    transition: 'all 0.2s',
                    width: '100%',
                    textAlign: 'left',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--surface-4)')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--surface-5)')}
                >
                  <div style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-1)', marginBottom: 4 }}>
                    {t('offline_conflicts.conflict_num', { id: conflict.id })}
                  </div>
                  <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>
                    {conflict.opId}
                  </div>
                  <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)', marginTop: 4 }}>
                    {t('offline_conflicts.strategy', { strategy: conflict.strategy })}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
