/**
 * BiEtlPanel.jsx — BI ETL Connector management.
 * Endpoints:
 *   GET  /bi/etl/connectors                          -> { connectors: [{connector_id, enabled, status, last_sync_at, last_records}], count }
 *   GET  /bi/etl/connectors/{id}                     -> detail with recent_log
 *   POST /bi/etl/connectors/{id}/sync                -> { task_id, connector_id, status, queue }
 *   GET  /bi/etl/connectors/{id}/log                 -> sync history
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { RefreshCw, CheckCircle, AlertCircle, Clock, ChevronDown, ChevronUp, Database } from 'lucide-react'
import { Card, Button, Spinner, EmptyState } from '../ui'
import { useToast } from '../../context/ToastContext'

const STATUS_META = {
  connected:    { label: 'Conectado',    color: 'var(--success)', Icon: CheckCircle },
  disconnected: { label: 'Desconectado', color: 'var(--text-3)',  Icon: AlertCircle },
  error:        { label: 'Error',        color: 'var(--danger)',  Icon: AlertCircle },
  syncing:      { label: 'Sincronizando', color: 'var(--warning)', Icon: Clock },
  queued:       { label: 'En cola',      color: 'var(--accent)',  Icon: Clock },
}

const CONNECTOR_LABEL = {
  azure_devops:  'Azure DevOps',
  jira:          'Jira',
  github:        'GitHub',
  gitlab:        'GitLab',
  servicenow:    'ServiceNow',
  zendesk:       'Zendesk',
  slack:         'Slack',
  m365:          'Microsoft 365',
  hubspot:       'HubSpot',
  salesforce:    'Salesforce',
  postgres:      'PostgreSQL',
  mysql:         'MySQL',
  s3:            'AWS S3',
}

const fieldLabel = {
  fontSize: 'var(--text-2xs)',
  fontWeight: 700,
  color: 'var(--text-3)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 6,
}
const chip = (color) => ({
  fontSize: 'var(--text-2xs)',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  color,
  background: `color-mix(in srgb, ${color} 15%, transparent)`,
  border: `1px solid color-mix(in srgb, ${color} 30%, transparent)`,
  borderRadius: 'var(--radius-full, 999px)',
  padding: '2px 9px',
  whiteSpace: 'nowrap',
})

function ConnectorCard({ connector, onSync, syncing, expanded, onToggleLog, log, logLoading }) {
  const meta = STATUS_META[connector.status] || STATUS_META.disconnected
  const Icon = meta.Icon
  const label = CONNECTOR_LABEL[connector.connector_id] || connector.connector_id

  return (
    <div style={{
      background: 'var(--surface-3)',
      border: '1px solid var(--surface-4)',
      borderRadius: 10,
      padding: '14px 16px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, flex: 1 }}>
          <Icon size={16} style={{ color: meta.color, flexShrink: 0 }} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-1)' }}>{label}</div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
              {connector.connector_id}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={chip(meta.color)}>{meta.label}</span>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => onSync(connector.connector_id)}
            disabled={syncing || !connector.enabled}
            loading={syncing}
            icon={<RefreshCw size={12} style={{ animation: syncing ? 'spin 1s linear infinite' : 'none' }} />}
            title={connector.enabled ? 'Sincronizar' : 'Conector deshabilitado'}
          >
            Sincronizar
          </Button>
        </div>
      </div>

      <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 14, fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
        <span>
          <span style={{ color: 'var(--text-3)' }}>Último sync:</span>{' '}
          <span style={{ color: 'var(--text-2)' }}>
            {connector.last_sync_at ? new Date(connector.last_sync_at).toLocaleString() : 'Nunca'}
          </span>
        </span>
        <span>
          <span style={{ color: 'var(--text-3)' }}>Registros:</span>{' '}
          <span style={{ color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>
            {(connector.last_records || 0).toLocaleString()}
          </span>
        </span>
        <button
          type="button"
          onClick={() => onToggleLog(connector.connector_id)}
          style={{
            marginLeft: 'auto',
            background: 'transparent', border: 'none', cursor: 'pointer',
            color: 'var(--accent)', fontSize: 'var(--text-xs)', fontFamily: 'inherit',
            display: 'inline-flex', alignItems: 'center', gap: 4, padding: 0,
          }}
        >
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {expanded ? 'Ocultar log' : 'Ver log'}
        </button>
      </div>

      {expanded && (
        <div style={{
          marginTop: 10,
          background: 'var(--surface-1)',
          border: '1px solid var(--surface-4)',
          borderRadius: 8,
          padding: 10,
          maxHeight: 220,
          overflowY: 'auto',
        }}>
          {logLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 12 }}><Spinner /></div>
          ) : !log || log.length === 0 ? (
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textAlign: 'center', padding: 8 }}>
              Sin entradas en el log.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {log.slice(0, 30).map((entry, i) => {
                const ok = entry.status === 'ok' || entry.status === 'success' || entry.success === true
                const c = ok ? 'var(--success)' : entry.status === 'error' ? 'var(--danger)' : 'var(--text-3)'
                return (
                  <div key={i} style={{ display: 'flex', gap: 10, fontSize: 'var(--text-xs)', color: 'var(--text-2)', alignItems: 'center' }}>
                    <span style={{ ...chip(c), flexShrink: 0 }}>{entry.status || (ok ? 'ok' : '—')}</span>
                    <span style={{ color: 'var(--text-3)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                      {entry.timestamp ? new Date(entry.timestamp).toLocaleString() : entry.at || ''}
                    </span>
                    <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {entry.message || (entry.records != null ? `${entry.records} registros` : '')}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function BiEtlPanel() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [syncingIds, setSyncingIds] = useState(new Set())
  const [expandedId, setExpandedId] = useState(null)

  const { data, isLoading } = useQuery({
    queryKey: ['bi-etl-connectors'],
    queryFn: () => api.get('/bi/etl/connectors').then(r => r.data),
    refetchInterval: 30_000,
  })

  const { data: logData, isLoading: logLoading } = useQuery({
    queryKey: ['bi-etl-connector-log', expandedId],
    queryFn: () => api.get(`/bi/etl/connectors/${expandedId}/log`).then(r => r.data),
    enabled: !!expandedId,
  })

  const syncMutation = useMutation({
    mutationFn: (connectorId) =>
      api.post(`/bi/etl/connectors/${connectorId}/sync`, { extra_config: {} }).then(r => r.data),
    onMutate: (id) => setSyncingIds(s => new Set([...s, id])),
    onSuccess: (res, id) => {
      const queue = res?.queue ? ` (queue ${res.queue})` : ''
      toast.success(`Sincronización encolada para ${CONNECTOR_LABEL[id] || id}${queue}`)
    },
    onError: (e, id) => toast.error(e?.response?.data?.detail || `Error al sincronizar ${id}`),
    onSettled: (_, __, id) => {
      setSyncingIds(s => { const next = new Set(s); next.delete(id); return next })
      qc.invalidateQueries({ queryKey: ['bi-etl-connectors'] })
      qc.invalidateQueries({ queryKey: ['bi-etl-connector-log', id] })
    },
  })

  const connectors = data?.connectors ?? []
  const enabledCount = connectors.filter(c => c.enabled).length
  const errorCount = connectors.filter(c => c.status === 'error').length
  const totalRecords = connectors.reduce((s, c) => s + (c.last_records || 0), 0)

  return (
    <Card style={{ padding: '20px 22px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Database size={18} style={{ color: 'var(--accent)' }} />
          <h2 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', margin: 0 }}>
            {t('bi.etl.title', 'Conectores ETL')}
          </h2>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={chip('var(--success)')}>{enabledCount} activos</span>
          {errorCount > 0 && <span style={chip('var(--danger)')}>{errorCount} con error</span>}
          <Button
            size="sm"
            variant="ghost"
            icon={<RefreshCw size={13} />}
            onClick={() => qc.invalidateQueries({ queryKey: ['bi-etl-connectors'] })}
            title={t('bi.etl.refresh', 'Refrescar lista')}
          >Refrescar</Button>
        </div>
      </div>

      {totalRecords > 0 && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginBottom: 12 }}>
          Total registros sincronizados: <strong style={{ color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{totalRecords.toLocaleString()}</strong>
        </div>
      )}

      {isLoading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}><Spinner /></div>
      ) : connectors.length === 0 ? (
        <EmptyState
          icon="🔌"
          title="Sin conectores configurados"
          description="Configura los conectores ETL desde Settings → AI Hub / Connectors."
        />
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
          gap: 10,
        }}>
          {connectors.map(c => (
            <ConnectorCard
              key={c.connector_id}
              connector={c}
              onSync={(id) => syncMutation.mutate(id)}
              syncing={syncingIds.has(c.connector_id)}
              expanded={expandedId === c.connector_id}
              onToggleLog={(id) => setExpandedId(prev => (prev === id ? null : id))}
              log={expandedId === c.connector_id ? (logData?.entries || logData?.log || logData?.items || logData?.recent_log || []) : []}
              logLoading={expandedId === c.connector_id && logLoading}
            />
          ))}
        </div>
      )}
    </Card>
  )
}
