/**
 * DataPlatformPage — Plataforma de datos: ETL, conectores,
 * streaming en tiempo real, snapshots versionados y linaje de plataforma.
 * Antes vivía en /bi tab "data".
 */
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import PageShell from '../components/layout/PageShell'
import PageHeader from '../components/layout/PageHeader'
import { Database, Eye, GitCompare, Radio, RefreshCw, Save } from 'lucide-react'
import { Button, Select, Input } from '../components/ui'
import { useAppLang } from '../i18n/AppLangContext'
import { biIntelligenceApi, biPlatformApi, wsApi, apiWsUrl } from '../services/api'
import type { DiferenciaDeInstantaneasBi } from '../services/api/tipos-bi'
import BiEtlPanel from '../components/bi/BiEtlPanel'
import BiO365Panel from '../components/bi/BiO365Panel'
import { formateadorDeFecha } from '../utils/helpers'
import { STALE_DEFAULT_MS, STALE_PREVIEW_MS, WS_STREAM_RECONNECT_MS } from '../constants/timings'
import { DATA_PREVIEW_ROWS } from '../constants/pagination'
import './DataPlatformPage.css'

interface StreamFrame {
  type?: string
  timestamp?: string
  anomaly_count?: number
}

export default function DataPlatformPage(): JSX.Element {
  const { t } = useAppLang()

  const [presetId, setPresetId] = useState('ops_delivery_mix')
  const [streamLive, setStreamLive] = useState(false)
  const [streamSnapshot, setStreamSnapshot] = useState<StreamFrame | null>(null)

  const [phase3Tick, setPhase3Tick] = useState(0)
  const [datasetKey, setDatasetKey] = useState('olap.fact_projects')
  const [snapshotDiff, setSnapshotDiff] = useState<DiferenciaDeInstantaneasBi | null>(null)

  const { data: reportPresets = [] } = useQuery({
    queryKey: ['data-platform-report-presets'],
    // El interceptor ya deja la lista en `r.data` (envelope APIListResponse).
    queryFn: () => biIntelligenceApi.reportPresets().then(r => r.data).catch(() => []),
    staleTime: STALE_DEFAULT_MS,
  })
  const { data: previewData, refetch: refetchPreview } = useQuery({
    queryKey: ['data-platform-preview', presetId],
    queryFn: () => biIntelligenceApi.previewPreset({ preset_id: presetId, limit: DATA_PREVIEW_ROWS }).then(r => r.data).catch(() => null),
    staleTime: STALE_PREVIEW_MS,
  })
  const { data: deliveryOverview } = useQuery({
    queryKey: ['data-platform-delivery'],
    queryFn: () => biIntelligenceApi.deliveryOverview().then(r => r.data).catch(() => null),
    staleTime: STALE_PREVIEW_MS,
  })
    const { data: phase3Lineage, refetch: refetchPhase3Lineage } = useQuery({
    queryKey: ['data-platform-lineage', phase3Tick],
    queryFn: () => biPlatformApi.lineage().then(r => r.data).catch(() => ({ edges: [], audit: [] })),
    staleTime: STALE_PREVIEW_MS,
  })
  const { data: phase3SnapshotItems = [], refetch: refetchPhase3Snapshots } = useQuery({
    queryKey: ['data-platform-snapshots', datasetKey, phase3Tick],
    queryFn: () => biPlatformApi.listSnapshots(datasetKey).then(r => r.data).catch(() => []),
    staleTime: STALE_PREVIEW_MS,
  })
  
  // WebSocket realtime stream
  useEffect(() => {
    if (!streamLive) return undefined
    let ws: WebSocket | null = null
    let closed = false
    async function connect() {
      try {
        // Ticket de un solo uso, como el resto de WebSockets: el token en la
        // URL se rechaza en producción y la pantalla reconectaba sin fin.
        const ticket = (await wsApi.ticket())?.data?.ticket
        if (!ticket || closed) return
        ws = new WebSocket(apiWsUrl(`/bi/intelligence/realtime/stream?ticket=${encodeURIComponent(ticket)}`))
        ws.onmessage = (ev) => {
          try {
            const data = JSON.parse(ev.data) as StreamFrame
            if (data?.type === 'bi_intelligence_snapshot') setStreamSnapshot(data)
          } catch (_e) { /* ignore malformed frames */ }
        }
        ws.onclose = () => { if (!closed && streamLive) setTimeout(connect, WS_STREAM_RECONNECT_MS) }
      } catch (_e) { /* keep UI responsive */ }
    }
    connect()
    return () => { closed = true; if (ws) ws.close() }
  }, [streamLive])

  const phase3LineageEdges = phase3Lineage?.edges ?? []

  async function handleCreateSnapshot() {
    try {
      await biPlatformApi.createSnapshot(datasetKey, {
        payload: { captured_at: new Date().toISOString(), source: 'data_platform_manual' },
      })
      setPhase3Tick(x => x + 1); await refetchPhase3Snapshots()
    } catch (_) { /* ignore */ }
  }
  async function handleDiffLastSnapshots() {
    const items = phase3SnapshotItems
    if (items.length < 2) return
    const fromId = items[items.length - 2]?.id
    const toId = items[items.length - 1]?.id
    if (!fromId || !toId) return
    try { const res = await biPlatformApi.diffSnapshots(datasetKey, fromId, toId); setSnapshotDiff(res?.data || null) } catch (_) { /* ignore */ }
  }

  return (
    <PageShell className="dpl-page">
      <PageHeader
        icon={<Database size={18} />}
        title={t('nav.data_platform')}
        subtitle={t('dataplatform.subtitulo')}
        showListExport={false}
      />

      <div className="u-stack-20">
        <BiEtlPanel />
        <BiO365Panel />

        <div className="dpl-grid">
          <div className="dpl-card">
            <div className="dpl-card-head"><div className="dpl-section-title">{t('dataplatform.presets')}</div></div>
            <div className="dpl-card-body">
              <Select suelto placeholder={false} aria-label={t('dataplatform.presets')} value={presetId} onChange={e => setPresetId(e.target.value)} className="dpl-input">
                {reportPresets.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </Select>
              <div><Button size="sm" variant="secondary" icon={<Eye size={14} />} onClick={() => refetchPreview()}>{t('dataplatform.previsualizar')}</Button></div>
              <div className="u-text3-xs">{t('dataplatform.filas_preview', { n: previewData?.count || 0 })}</div>
              <div className="u-text3-xs">
                {t('dataplatform.envios', { activos: deliveryOverview?.active ?? 0, errores: deliveryOverview?.errored ?? 0 })}
              </div>
            </div>
          </div>
          <div className="dpl-card">
            <div className="dpl-card-head"><div className="dpl-section-title">{t('dataplatform.streaming')}</div></div>
            <div className="dpl-card-body">
              <div>
                <Button size="sm" variant={streamLive ? 'primary' : 'secondary'} icon={<Radio size={14} />} onClick={() => setStreamLive(v => !v)}>
                  {t(streamLive ? 'dataplatform.streaming_activo' : 'dataplatform.activar_streaming')}
                </Button>
              </div>
              <div className="u-text3-xs">
                {streamSnapshot?.timestamp
                  ? t('dataplatform.instantanea', { hora: formateadorDeFecha({ hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(streamSnapshot.timestamp)), n: streamSnapshot.anomaly_count ?? 0 })
                  : t('dataplatform.sin_instantanea')}
              </div>
            </div>
          </div>
          <div className="dpl-card">
            <div className="dpl-card-head"><div className="dpl-section-title">{t('dataplatform.linaje')}</div></div>
            <div className="dpl-card-body dpl-card-body--tight">
              <div className="u-text2-sm">
                {t('dataplatform.aristas_y_versiones', { aristas: phase3LineageEdges.length, versiones: phase3SnapshotItems.length })}
              </div>
              <Input aria-label={t('dataplatform.dataset')} value={datasetKey} onChange={e => setDatasetKey(e.target.value)} placeholder={t('dataplatform.dataset')} inputClassName="dpl-input" />
              <div className="u-wrap-8">
                <Button size="sm" icon={<Save size={14} />} onClick={handleCreateSnapshot}>{t('dataplatform.crear_version')}</Button>
                <Button size="sm" variant="secondary" icon={<GitCompare size={14} />} onClick={handleDiffLastSnapshots} disabled={phase3SnapshotItems.length < 2}>{t('dataplatform.diff_ultimos_2')}</Button>
                <Button size="sm" variant="ghost" icon={<RefreshCw size={14} />} onClick={() => refetchPhase3Lineage()}>{t('dataplatform.refrescar')}</Button>
              </div>
              {snapshotDiff && <div className="u-text3-xs">{t('dataplatform.cambios', { n: snapshotDiff.change_count })}</div>}
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  )
}
