/**
 * OfflineIndicator — shows network status + pending offline queue info
 *
 * Mount anywhere in the app shell (e.g. Layout.jsx) — it listens to
 * navigator.onLine events and shows a banner + pending count badge.
 */

import { useState, useEffect } from 'react';
import { pendingCount, syncPending } from '../services/offlineQueue';
import api from '../services/api';

export default function OfflineIndicator() {
  const [online, setOnline]   = useState(navigator.onLine);
  const [pending, setPending] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [lastSync, setLastSync] = useState(null);

  // Refresh pending count
  const refreshCount = async () => {
    try { setPending(await pendingCount()); } catch { /* ignore */ }
  };

  useEffect(() => {
    refreshCount();

    const onOnline  = () => { setOnline(true);  refreshCount(); };
    const onOffline = () => { setOnline(false); refreshCount(); };
    window.addEventListener('online',  onOnline);
    window.addEventListener('offline', onOffline);

    // Poll pending count while offline (every 10 s)
    const poll = setInterval(refreshCount, 10_000);
    return () => {
      window.removeEventListener('online',  onOnline);
      window.removeEventListener('offline', onOffline);
      clearInterval(poll);
    };
  }, []);

  const handleSync = async () => {
    setSyncing(true);
    try {
      const { synced, failed } = await syncPending(api);
      await refreshCount();
      setLastSync({ synced, failed, at: new Date().toLocaleTimeString() });
    } finally {
      setSyncing(false);
    }
  };

  // Nothing to show when online and no pending entries
  if (online && pending === 0) return null;

  return (
    <div style={{
      position: 'fixed',
      bottom: 16,
      right: 16,
      zIndex: 9000,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'flex-end',
      gap: 6,
      pointerEvents: 'none',
    }}>
      {/* Last sync toast */}
      {lastSync && (
        <div style={{
          background: lastSync.failed ? '#744210' : '#1a3a1a',
          border: `1px solid ${lastSync.failed ? '#d69e2e' : '#276227'}`,
          borderRadius: 8,
          padding: '6px 12px',
          fontSize: 12,
          color: lastSync.failed ? '#f6e05e' : '#68d391',
          pointerEvents: 'auto',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}>
          {lastSync.failed
            ? `⚠ Sincronizados ${lastSync.synced}, fallaron ${lastSync.failed} — ${lastSync.at}`
            : `✅ ${lastSync.synced} imputaciones sincronizadas — ${lastSync.at}`
          }
          <button onClick={() => setLastSync(null)}
            style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0, fontSize: 11 }}>
            ✕
          </button>
        </div>
      )}

      {/* Main status pill */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '7px 14px',
        borderRadius: 20,
        background: online ? '#1a3a1a' : '#2d1a1a',
        border: `1px solid ${online ? '#276227' : '#822'}`,
        boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
        pointerEvents: 'auto',
      }}>
        {/* Dot */}
        <span style={{
          width: 8, height: 8, borderRadius: '50%',
          background: online ? '#68d391' : '#fc8181',
          boxShadow: `0 0 6px ${online ? '#68d391' : '#fc8181'}`,
          flexShrink: 0,
        }} />

        <span style={{ fontSize: 12, color: online ? '#68d391' : '#fc8181', fontWeight: 500 }}>
          {online ? 'En línea' : 'Sin conexión'}
        </span>

        {pending > 0 && (
          <>
            <span style={{
              background: '#744210',
              color: '#f6e05e',
              borderRadius: 10,
              padding: '1px 7px',
              fontSize: 11,
              fontWeight: 700,
            }}>
              {pending} pendiente{pending !== 1 ? 's' : ''}
            </span>

            {online && (
              <button
                onClick={handleSync}
                disabled={syncing}
                style={{
                  background: '#2d6a2d',
                  border: '1px solid #276227',
                  borderRadius: 6,
                  color: '#68d391',
                  fontSize: 11,
                  padding: '2px 8px',
                  cursor: syncing ? 'wait' : 'pointer',
                  fontFamily: 'inherit',
                }}>
                {syncing ? '⏳' : '⚡ Sincronizar'}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
