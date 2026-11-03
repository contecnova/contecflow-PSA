/**
 * DataPlatformPage — Plataforma de datos: ETL, conectores, embed SDK,
 * streaming en tiempo real, snapshots versionados y linaje de plataforma.
 * Antes vivía en /bi tab "data".
 */
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import PageShell from '../components/layout/PageShell'
import PageHeader from '../components/layout/PageHeader'
import { Database } from 'lucide-react'
import { COLOR, alpha } from '../constants/theme'
import { useAppLang } from '../i18n/AppLangContext'
import useMediaQuery from '../hooks/useMediaQuery'
import { biIntelligenceApi, biPlatformApi } from '../services/api'
import BiEtlPanel from '../components/bi/BiEtlPanel'
import BiO365Panel from '../components/bi/BiO365Panel'

interface ConnectorCfg {
  enabled?: boolean
  last_sync_at?: string
}

interface ConnectorsResponse {
  items?: Record<string, ConnectorCfg>
}

interface ReportPresetItem {
  id: string
  name: string
}

interface ReportPresetsResponse {
  items?: ReportPresetItem[]
}

interface PlatformManifest {
  name?: string
  version?: string
  features?: string[]
}

interface CatalogConnectorCfg {
  enabled?: boolean
}

interface CatalogResponse {
  items?: Record<string, CatalogConnectorCfg>
}

interface CustomConnectorItem {
  id: string | number
  name?: string
  endpoint?: string
}

interface CustomConnectorsResponse {
  items?: CustomConnectorItem[]
}

interface LineageResponse {
  edges?: unknown[]
}

interface SnapshotItem {
  id: string | number
}

interface SnapshotsResponse {
  items?: SnapshotItem[]
}

interface SnapshotDiff {
  change_count?: number
}

interface StreamFrame {
  type?: string
  timestamp?: string
}

const S = {
  card:        { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14, overflow: 'hidden' },
  cardPad:     { padding: '20px 24px' },
  sectionTitle:{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.09em', margin: 0 },
  input:       { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', color: 'var(--text-1)', borderRadius: 8, padding: '9px 13px', fontSize: 'var(--text-base)', fontFamily: 'inherit', outline: 'none', width: '100%' },
  btnSecondary:{ padding: '7px 16px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 'var(--text-sm)', fontFamily: 'inherit' },
  btnAccentOutline: (c: string = COLOR.accent) => ({ padding: '7px 14px', borderRadius: 8, border: `1px solid ${c}`, background: alpha(c, '18'), color: c, cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 600, fontFamily: 'inherit' }),
}

const getLocale = (lang?: string) => (lang === 'en' ? 'en-US' : 'es-ES')

function SectionHeading({ title, description }: { title?: React.ReactNode; description?: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <h2 style={{ fontSize: 'var(--text-md-em)', fontWeight: 700, color: 'var(--text-1)', margin: '0 0 4px' }}>{title}</h2>
      {description && <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', margin: 0 }}>{description}</p>}
    </div>
  )
}

export default function DataPlatformPage(): JSX.Element {
  const { t } = useAppLang()
  const { lang } = useAppLang()
  const isMobile = useMediaQuery('(max-width: 900px)')

  const [phase2Tick, setPhase2Tick] = useState(0)
  const [presetId, setPresetId] = useState('ops_delivery_mix')
  const [streamLive, setStreamLive] = useState(false)
  const [streamSnapshot, setStreamSnapshot] = useState<StreamFrame | null>(null)

  const [phase3Tick, setPhase3Tick] = useState(0)
  const [embedToken, setEmbedToken] = useState('')
  const [customConnectorName, setCustomConnectorName] = useState('')
  const [customConnectorEndpoint, setCustomConnectorEndpoint] = useState('')
  const [datasetKey, setDatasetKey] = useState('olap.fact_projects')
  const [snapshotDiff, setSnapshotDiff] = useState<SnapshotDiff | null>(null)

  const { data: connectorsDataRaw, refetch: refetchConnectors } = useQuery({
    queryKey: ['data-platform-connectors', phase2Tick],
    queryFn: () => biIntelligenceApi.listConnectors().then(r => r.data).catch(() => ({ items: {} })),
    staleTime: 15_000,
  })
  const connectorsData = (connectorsDataRaw ?? { items: {} }) as ConnectorsResponse
  const { data: reportPresetsRaw } = useQuery({
    queryKey: ['data-platform-report-presets'],
    queryFn: () => biIntelligenceApi.reportPresets().then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 60_000,
  })
  const reportPresets = (reportPresetsRaw ?? { items: [] }) as ReportPresetsResponse
  const { data: previewData, refetch: refetchPreview } = useQuery({
    queryKey: ['data-platform-preview', presetId, phase2Tick],
    queryFn: () => biIntelligenceApi.previewPreset({ preset_id: presetId, limit: 20 }).then(r => r.data).catch(() => null),
    staleTime: 20_000,
  })
  const { data: deliveryOverview } = useQuery({
    queryKey: ['data-platform-delivery', phase2Tick],
    queryFn: () => biIntelligenceApi.deliveryOverview().then(r => r.data).catch(() => null),
    staleTime: 20_000,
  })
  const { data: phase3ManifestRaw } = useQuery({
    queryKey: ['data-platform-manifest'],
    queryFn: () => biPlatformApi.sdkManifest().then(r => r.data).catch(() => null),
    staleTime: 60_000,
  })
  const phase3Manifest = (phase3ManifestRaw ?? null) as PlatformManifest | null
  const { data: phase3CatalogRaw, refetch: refetchPhase3Catalog } = useQuery({
    queryKey: ['data-platform-catalog', phase3Tick],
    queryFn: () => biPlatformApi.connectorCatalog().then(r => r.data).catch(() => ({ count: 0, items: {} })),
    staleTime: 20_000,
  })
  const phase3Catalog = (phase3CatalogRaw ?? { items: {} }) as CatalogResponse
  const { data: phase3CustomRaw, refetch: refetchPhase3Custom } = useQuery({
    queryKey: ['data-platform-custom', phase3Tick],
    queryFn: () => biPlatformApi.listCustomConnectors().then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 20_000,
  })
  const phase3Custom = (phase3CustomRaw ?? { items: [] }) as CustomConnectorsResponse
  const { data: phase3LineageRaw, refetch: refetchPhase3Lineage } = useQuery({
    queryKey: ['data-platform-lineage', phase3Tick],
    queryFn: () => biPlatformApi.lineage().then(r => r.data).catch(() => ({ edges: [], audit: [] })),
    staleTime: 20_000,
  })
  const phase3Lineage = (phase3LineageRaw ?? { edges: [] }) as LineageResponse
  const { data: phase3SnapshotsRaw, refetch: refetchPhase3Snapshots } = useQuery({
    queryKey: ['data-platform-snapshots', datasetKey, phase3Tick],
    queryFn: () => biPlatformApi.listSnapshots(datasetKey).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 20_000,
  })
  const phase3Snapshots = (phase3SnapshotsRaw ?? { items: [] }) as SnapshotsResponse

  // WebSocket realtime stream
  useEffect(() => {
    if (!streamLive) return undefined
    let ws: WebSocket | null = null
    let closed = false
    async function connect() {
      try {
        const tokenRes = await biIntelligenceApi.realtimeToken()
        const token = tokenRes?.data?.token
        if (!token) return
        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        ws = new WebSocket(`${proto}//${window.location.host}/api/v1/bi/intelligence/realtime/stream?token=${encodeURIComponent(token)}`)
        ws.onmessage = (ev) => {
          try {
            const data = JSON.parse(ev.data) as StreamFrame
            if (data?.type === 'bi_intelligence_snapshot') setStreamSnapshot(data)
          } catch (_e) { /* ignore malformed frames */ }
        }
        ws.onclose = () => { if (!closed && streamLive) setTimeout(connect, 2000) }
      } catch (_e) { /* keep UI responsive */ }
    }
    connect()
    return () => { closed = true; if (ws) ws.close() }
  }, [streamLive])

  const connectors = Object.entries(connectorsData?.items || {})
  const phase3CatalogEntries = Object.entries(phase3Catalog?.items || {})
  const phase3CustomItems = phase3Custom?.items || []
  const phase3LineageEdges = phase3Lineage?.edges || []
  const phase3SnapshotItems = phase3Snapshots?.items || []

  async function handleToggleConnector(name: string, enabled: boolean) {
    try { await biIntelligenceApi.patchConnector(name, { enabled }); setPhase2Tick(x => x + 1); await refetchConnectors() } catch (_) { /* ignore */ }
  }
  async function handleSyncConnector(name: string) {
    try { await biIntelligenceApi.syncConnector(name); setPhase2Tick(x => x + 1); await refetchConnectors() } catch (_) { /* ignore */ }
  }
  async function handleIssueEmbedToken() {
    try { const res = await biPlatformApi.embedToken({ dashboard_key: 'executive', expires_minutes: 60 }); setEmbedToken(res?.data?.token || '') } catch (_) { /* ignore */ }
  }
  async function handleToggleCatalogConnector(name: string, enabled: boolean) {
    try { await biPlatformApi.patchCatalogConnector(name, { enabled }); setPhase3Tick(x => x + 1); await refetchPhase3Catalog() } catch (_) { /* ignore */ }
  }
  async function handleCreateCustomConnector() {
    const name = customConnectorName.trim()
    const endpoint = customConnectorEndpoint.trim()
    if (!name || !endpoint) return
    try {
      await biPlatformApi.createCustomConnector({ name, endpoint, kind: 'rest', auth_type: 'api_key', enabled: true })
      setCustomConnectorName(''); setCustomConnectorEndpoint('')
      setPhase3Tick(x => x + 1); await refetchPhase3Custom()
    } catch (_) { /* ignore */ }
  }
  async function handleTestCustomConnector(id: string | number) {
    try { await biPlatformApi.testCustomConnector(id); setPhase3Tick(x => x + 1); await refetchPhase3Custom() } catch (_) { /* ignore */ }
  }
  async function handleCreateSnapshot() {
    try {
      await biPlatformApi.createSnapshot(datasetKey, {
        payload: { captured_at: new Date().toISOString(), source: 'data_platform_manual' },
      })
      setPhase3Tick(x => x + 1); await refetchPhase3Snapshots()
    } catch (_) { /* ignore */ }
  }
  async function handleDiffLastSnapshots() {
    const items = phase3Snapshots?.items || []
    if (items.length < 2) return
    const fromId = items[items.length - 2]?.id
    const toId = items[items.length - 1]?.id
    if (!fromId || !toId) return
    try { const res = await biPlatformApi.diffSnapshots(datasetKey, fromId, toId); setSnapshotDiff(res?.data || null) } catch (_) { /* ignore */ }
  }

  return (
    <PageShell style={isMobile ? { paddingLeft: 14, paddingRight: 14 } : undefined}>
      <PageHeader
        icon={<Database size={18} />}
        title="Data Platform"
        subtitle="ETL, conectores, embed SDK, streaming y snapshots versionados"
      showListExport={false}
      />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

        <BiEtlPanel />
        <BiO365Panel />

        {connectors.length > 0 && (
          <div style={S.card}>
            <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>{t('dataplatform.conectores_de_datos_activos')}</div></div>
            <div style={{ ...S.cardPad, display: 'flex', flexDirection: 'column', gap: 10 }}>
              {connectors.map(([name, cfg]) => (
                <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', background: 'var(--surface-3)', borderRadius: 8 }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: cfg.enabled ? COLOR.success : 'var(--text-4)', flexShrink: 0 }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-1)' }}>{name}</div>
                    <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)' }}>{cfg.last_sync_at ? `Último sync: ${new Date(cfg.last_sync_at).toLocaleString(getLocale(lang))}` : 'Sin sincronizar'}</div>
                  </div>
                  <button onClick={() => handleToggleConnector(name, !cfg.enabled)} style={S.btnSecondary}>{cfg.enabled ? 'Desactivar' : 'Activar'}</button>
                  <button onClick={() => handleSyncConnector(name)} style={S.btnAccentOutline()}>Sync</button>
                </div>
              ))}
            </div>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 14 }}>
          <div style={S.card}>
            <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>Report presets — Preview</div></div>
            <div style={{ ...S.cardPad, display: 'grid', gap: 10 }}>
              <select value={presetId} onChange={e => setPresetId(e.target.value)} style={S.input}>
                {(reportPresets?.items || []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <button onClick={() => refetchPreview()} style={S.btnAccentOutline()}>Previsualizar preset</button>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>Filas preview: {previewData?.count || 0}</div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
                Delivery activo: {deliveryOverview?.active ?? 0} · errores: {deliveryOverview?.errored ?? 0}
              </div>
            </div>
          </div>
          <div style={S.card}>
            <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>Streaming en tiempo real</div></div>
            <div style={{ ...S.cardPad, display: 'grid', gap: 10 }}>
              <button onClick={() => setStreamLive(v => !v)}
                style={{ ...S.btnAccentOutline(streamLive ? COLOR.success : 'var(--surface-5)'), color: streamLive ? COLOR.success : 'var(--text-2)' }}>
                {streamLive ? '● Streaming activo' : 'Activar streaming'}
              </button>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
                {streamSnapshot?.timestamp ? `Snapshot: ${new Date(streamSnapshot.timestamp).toLocaleTimeString(getLocale(lang))}` : 'Sin snapshot reciente'}
              </div>
            </div>
          </div>
        </div>

        <div>
          <SectionHeading title="Plataforma BI" description="Embed SDK, catálogo de conectores y conectores personalizados" />
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fit, minmax(300px, 1fr))', gap: 14 }}>

            <div style={S.card}>
              <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>Embed SDK</div></div>
              <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{phase3Manifest?.name || 'Contecflow BI Embed SDK'} v{phase3Manifest?.version || '1.0.0'}</div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>Features: {(phase3Manifest?.features || []).join(', ') || 'n/a'}</div>
                <button onClick={handleIssueEmbedToken} style={S.btnAccentOutline()}>Emitir token embed</button>
                {embedToken && <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', wordBreak: 'break-all' }}>JWT: {embedToken.slice(0, 70)}...</div>}
              </div>
            </div>

            <div style={S.card}>
              <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>{t('dataplatform.catalogo_de_conectores')}{phase3CatalogEntries.filter(([, cfg]) => !!cfg?.enabled).length} activos)</div></div>
              <div style={{ ...S.cardPad, display: 'grid', gap: 6 }}>
                {phase3CatalogEntries.slice(0, 8).map(([name, cfg]) => (
                  <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: cfg.enabled ? COLOR.success : 'var(--text-4)', flexShrink: 0 }} />
                    <span style={{ flex: 1, fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{name}</span>
                    <button onClick={() => handleToggleCatalogConnector(name, !cfg.enabled)}
                      style={{ ...S.btnSecondary, padding: '3px 10px', fontSize: 'var(--text-xs)' }}>{cfg.enabled ? 'Off' : 'On'}</button>
                  </div>
                ))}
                {phase3CatalogEntries.length === 0 && <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>{t('dataplatform.sin_conectores_en_catalogo')}</div>}
              </div>
            </div>

            <div style={S.card}>
              <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>Conectores personalizados</div></div>
              <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
                <input value={customConnectorName} onChange={e => setCustomConnectorName(e.target.value)} placeholder="Nombre" style={S.input} />
                <input value={customConnectorEndpoint} onChange={e => setCustomConnectorEndpoint(e.target.value)} placeholder="Endpoint URL" style={S.input} />
                <button onClick={handleCreateCustomConnector} style={S.btnAccentOutline()}>Crear conector</button>
                {phase3CustomItems.slice(0, 3).map(c => (
                  <div key={c.id} style={{ border: '1px solid var(--surface-4)', borderRadius: 8, padding: 8 }}>
                    <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)', fontWeight: 600 }}>{c.name}</div>
                    <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)' }}>{c.endpoint}</div>
                    <button onClick={() => handleTestCustomConnector(c.id)} style={{ ...S.btnSecondary, padding: '3px 10px', fontSize: 'var(--text-xs)', marginTop: 6 }}>Test</button>
                  </div>
                ))}
              </div>
            </div>

            <div style={S.card}>
              <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>Lineage y versiones</div></div>
              <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>
                  Edges: {phase3LineageEdges.length} · Snapshots: {phase3SnapshotItems.length}
                </div>
                <input value={datasetKey} onChange={e => setDatasetKey(e.target.value)} placeholder="dataset key" style={S.input} />
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <button onClick={handleCreateSnapshot} style={S.btnAccentOutline()}>Crear snapshot</button>
                  <button onClick={handleDiffLastSnapshots} style={S.btnSecondary}>{t('dataplatform.diff_ultimos_2')}</button>
                  <button onClick={() => refetchPhase3Lineage()} style={S.btnSecondary}>Refrescar</button>
                </div>
                {snapshotDiff && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>Cambios: {snapshotDiff?.change_count ?? 0}</div>}
              </div>
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  )
}
