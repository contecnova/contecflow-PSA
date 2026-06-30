/**
 * OfflineIndicator — shows network status + offline queue info with advanced sync stats
 * 
 * Features:
 * - Network status badge with pulse animation
 * - Pending operations counter
 * - Sync progress indicator
 * - Conflict alerts
 * - Manual sync button with retry tracking
 */

import { useState, useEffect } from 'react';
import { syncPending } from '../services/offlineQueue';
import {
  useOfflineSync,
  getSyncStats,
} from '../services/offlineSync';
import api from '../services/api';
import { useAppT } from '../i18n/AppLangContext';

export default function OfflineIndicator() {
  const t = useAppT();
  const {
    isOnline, 
    pendingCount: offlineSyncCount, 
    conflictCount, 
    syncInProgress,
    lastSyncResult,
  } = useOfflineSync(api);
  
  const [syncStats, setSyncStats] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [manualSyncing, setManualSyncing] = useState(false);

  useEffect(() => {
    const updateStats = async () => {
      const stats = await getSyncStats();
      setSyncStats(stats);
    };
    updateStats();
    const interval = setInterval(updateStats, 3000);
    return () => clearInterval(interval);
  }, [isOnline, syncInProgress]);

  const handleManualSync = async () => {
    setManualSyncing(true);
    try {
      await syncPending(api);
      const stats = await getSyncStats();
      setSyncStats(stats);
    } catch (e) {
      console.error('[OfflineIndicator] Manual sync error:', e);
    } finally {
      setManualSyncing(false);
    }
  };

  // Nothing to show when online and no pending entries
  const totalPending = (offlineSyncCount ?? 0) + (syncStats?.pendingOpsCount ?? 0);
  const totalConflicts = conflictCount ?? (syncStats?.pendingConflictsCount ?? 0);
  
  if (isOnline && totalPending === 0 && totalConflicts === 0) {
    return null;
  }

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 16,
        right: 16,
        zIndex: 9000,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-end',
        gap: 8,
        pointerEvents: 'none',
      }}
    >
      {/* Conflict Alert */}
      {totalConflicts > 0 && (
        <div
          style={{
            background: 'color-mix(in srgb, var(--orange) 25%, var(--surface-1))',
            border: '1px solid var(--orange)',
            borderRadius: 8,
            padding: '8px 12px',
            fontSize: "var(--text-sm)",
            color: 'var(--orange)',
            pointerEvents: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            animation: 'pulse 2s infinite',
          }}
        >
          <span style={{ fontSize: "var(--text-md)" }}>⚠️</span>
          <span>{t('offline_indicator.conflicts_pending', { count: totalConflicts })}</span>
        </div>
      )}

      {/* Main status pill */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => setExpanded(!expanded)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setExpanded((prev) => !prev);
          }
        }}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 14px',
          borderRadius: 20,
          background: isOnline ? 'var(--success-bg)' : 'var(--danger-bg)',
          border: `1px solid ${isOnline ? 'var(--success-border)' : 'var(--danger-border)'}`,
          boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
          pointerEvents: 'auto',
          cursor: 'pointer',
          userSelect: 'none',
        }}
      >
        {/* Pulsing dot */}
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: isOnline ? 'var(--success)' : 'var(--danger)',
            boxShadow: `0 0 6px ${isOnline ? 'var(--success)' : 'var(--danger)'}`,
            flexShrink: 0,
            animation: isOnline ? 'pulse-glow 2s infinite' : 'pulse-glow-offline 2s infinite',
          }}
        />

        <span
          style={{
            fontSize: "var(--text-sm)",
            color: isOnline ? 'var(--success)' : 'var(--danger)',
            fontWeight: 500,
          }}
        >
          {isOnline ? t('offline_indicator.online') : t('offline_indicator.offline')}
        </span>

        {syncInProgress && (
          <span style={{ fontSize: "var(--text-2xs)", color: 'var(--warning)', marginLeft: 4 }}>{t('offline_indicator.syncing')}</span>
        )}

        {totalPending > 0 && (
          <span
            style={{
              background: 'color-mix(in srgb, var(--warning) 30%, var(--surface-1))',
              color: 'var(--warning)',
              borderRadius: 10,
              padding: '1px 7px',
              fontSize: "var(--text-xs)",
              fontWeight: 700,
            }}
          >
            {totalPending}
          </span>
        )}

        {/* Expand indicator */}
        <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', marginLeft: 4 }}>
          {expanded ? '▼' : '▶'}
        </span>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div
          style={{
            background: 'var(--surface-2)',
            border: '1px solid var(--surface-5)',
            borderRadius: 8,
            padding: 12,
            fontSize: "var(--text-xs)",
            color: 'var(--text-1)',
            minWidth: 250,
            maxWidth: 350,
            pointerEvents: 'auto',
            boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
          }}
        >
          {/* Stats */}
          <div style={{ marginBottom: 12, paddingBottom: 12, borderBottom: '1px solid var(--surface-5)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <span>{t('offline_indicator.pending_operations')}</span>
              <strong style={{ color: 'var(--warning)' }}>{totalPending}</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <span>{t('offline_indicator.pending_conflicts')}</span>
              <strong style={{ color: totalConflicts > 0 ? 'var(--danger)' : 'var(--success)' }}>
                {totalConflicts}
              </strong>
            </div>
            {syncStats?.resolvedConflictsCount > 0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>{t('offline_indicator.resolved_conflicts')}</span>
                <strong style={{ color: 'var(--success)' }}>{syncStats.resolvedConflictsCount}</strong>
              </div>
            )}
          </div>

          {/* Last sync result */}
          {lastSyncResult && (
            <div style={{ marginBottom: 12, paddingBottom: 12, borderBottom: '1px solid var(--surface-5)', fontSize: "var(--text-2xs)" }}>
              <div style={{ fontWeight: 600, marginBottom: 6, color: 'var(--text-2)' }}>{t('offline_indicator.last_sync')}</div>
              <div>{t('offline_indicator.synced_count', { count: lastSyncResult.synced })}</div>
              {lastSyncResult.failed > 0 && (
                <div style={{ color: 'var(--danger)' }}>{t('offline_indicator.failed_count', { count: lastSyncResult.failed })}</div>
              )}
              {lastSyncResult.conflicts > 0 && (
                <div style={{ color: 'var(--orange)' }}>{t('offline_indicator.conflicts_count', { count: lastSyncResult.conflicts })}</div>
              )}
            </div>
          )}

          {/* Sync button */}
          {isOnline && totalPending > 0 && (
            <button
              onClick={handleManualSync}
              disabled={manualSyncing || syncInProgress}
              style={{
                width: '100%',
                padding: '6px 12px',
                background: 'var(--accent)',
                border: '1px solid var(--accent-dim)',
                borderRadius: 4,
                color: '#fff',
                fontSize: "var(--text-xs)",
                fontWeight: 500,
                cursor: manualSyncing || syncInProgress ? 'wait' : 'pointer',
                opacity: manualSyncing || syncInProgress ? 0.7 : 1,
              }}
            >
              {manualSyncing || syncInProgress ? t('offline_indicator.syncing_now') : t('offline_indicator.sync_now_btn')}
            </button>
          )}

          {isOnline && totalPending === 0 && totalConflicts === 0 && (
            <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: "var(--text-2xs)" }}>
              {t('offline_indicator.all_synced')}
            </div>
          )}
        </div>
      )}

      <style>{`
        @keyframes pulse-glow {
          0%, 100% { box-shadow: 0 0 6px var(--success); opacity: 1; }
          50% { box-shadow: 0 0 12px var(--success); opacity: 0.8; }
        }
        @keyframes pulse-glow-offline {
          0%, 100% { box-shadow: 0 0 6px var(--danger); opacity: 1; }
          50% { box-shadow: 0 0 12px var(--danger); opacity: 0.8; }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.8; }
        }
      `}</style>
    </div>
  );
}
