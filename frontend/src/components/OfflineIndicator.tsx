/**
 * OfflineIndicator — estado de red y cola offline de imputaciones
 * (`services/offlineQueue`, la única cola que la app usa).
 *
 * - Pastilla de estado con el número de imputaciones pendientes
 * - Detalle desplegable con el resultado de la última sincronización
 * - Botón de sincronización manual
 */

import { type CSSProperties, useState } from 'react';
import { syncPending } from '../services/offlineQueue';
import useOfflineSync from '../hooks/useOfflineSync';
import api from '../services/api';
import { useAppT } from '../i18n/AppLangContext';
import './OfflineIndicator.css'

type ResultadoDeSync = Awaited<ReturnType<typeof syncPending>>;

export default function OfflineIndicator() {
  const t = useAppT();
  const { isOnline, pendingCount: totalPending, refresh } = useOfflineSync();
  const [expanded, setExpanded] = useState(false);
  const [manualSyncing, setManualSyncing] = useState(false);
  const [lastSyncResult, setLastSyncResult] = useState<ResultadoDeSync | null>(null);

  const handleManualSync = async () => {
    setManualSyncing(true);
    try {
      setLastSyncResult(await syncPending(api));
    } catch (e) {
      console.error('[OfflineIndicator] Manual sync error:', e);
    } finally {
      setManualSyncing(false);
      refresh();
    }
  };

  // Nothing to show when online and no pending entries
  if (isOnline && totalPending === 0) {
    return null;
  }

  return (
    <div
      className="offlindi-stack-1"
    >
      {/* Main status pill */}
      <div className={`offlindi-row-2 offlinei-sx1 offline-indicator-e1 ${isOnline ? 'offline-indicator-m2' : 'offline-indicator-m3'}`}
        role="button"
        tabIndex={0}
        onClick={() => setExpanded(!expanded)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setExpanded((prev) => !prev);
          }
        }}
        style={{ '--offline-indicator-border': `1px solid ${isOnline ? 'var(--success-border)' : 'var(--danger-border)'}` } as CSSProperties}
      >
        {/* Pulsing dot */}
        <span className={`offlindi-box-7 offline-indicator-e4 ${isOnline ? 'offline-indicator-m5' : 'offline-indicator-m6'}`}
          style={{ '--offline-indicator-box-shadow': `0 0 6px ${isOnline ? 'var(--success)' : 'var(--danger)'}` } as CSSProperties}
        />

        <span className={`offlindi-txt-2 ${isOnline ? 'offline-indicator-m7' : 'offline-indicator-m8'}`}
        >
          {isOnline ? t('offline_indicator.online') : t('offline_indicator.offline')}
        </span>

        {manualSyncing && (
          <span className="offlindi-box-1">{t('offline_indicator.syncing')}</span>
        )}

        {totalPending > 0 && (
          <span
            className="offlindi-box-2"
          >
            {totalPending}
          </span>
        )}

        {/* Expand indicator */}
        <span className="offlindi-box-3">
          {expanded ? '▼' : '▶'}
        </span>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="offlinei-sx2"
        >
          {/* Stats */}
          <div className="offlindi-box-4">
            <div className="offlindi-row-1">
              <span>{t('offline_indicator.pending_operations')}</span>
              <strong className="u-warning">{totalPending}</strong>
            </div>
          </div>

          {/* Last sync result */}
          {lastSyncResult && (
            <div className="offlindi-box-5">
              <div className="offlindi-box-6">{t('offline_indicator.last_sync')}</div>
              <div>{t('offline_indicator.synced_count', { count: lastSyncResult.synced })}</div>
              {lastSyncResult.failed > 0 && (
                <div className="u-danger">{t('offline_indicator.failed_count', { count: lastSyncResult.failed })}</div>
              )}
            </div>
          )}

          {/* Sync button */}
          {isOnline && totalPending > 0 && (
            <button className={`offlindi-box-8 ${manualSyncing ? 'offline-indicator-m9' : 'offline-indicator-m10'}`}
              onClick={handleManualSync}
              disabled={manualSyncing}
            >
              {manualSyncing ? t('offline_indicator.syncing_now') : t('offline_indicator.sync_now_btn')}
            </button>
          )}

          {isOnline && totalPending === 0 && (
            <div className="offlindi-txt-1">
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
