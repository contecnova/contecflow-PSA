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
import { Button, Select, Input, EstadoDeError } from '../components/ui'
import { useToast } from '../context/ToastContext'
import { useAppLang } from '../i18n/AppLangContext'
import { biIntelligenceApi, biPlatformApi, wsApi, apiWsUrl } from '../services/api'
import type { DiferenciaDeInstantaneasBi } from '../services/api/tipos-bi'
import BiEtlPanel from '../components/bi/BiEtlPanel'
import BiO365Panel from '../components/bi/BiO365Panel'
import { extractErr, formateadorDeFecha } from '../utils/helpers'
import { STALE_DEFAULT_MS, STALE_PREVIEW_MS, WS_STREAM_RECONNECT_MS } from '../constants/timings'
import { DATA_PREVIEW_ROWS } from '../constants/pagination'
import './DataPlatformPage.css'

/** Conjunto de datos con el que arranca el campo de linaje y versiones (editable por quien opera; 04 M10, 23-11-2026). */
const DATASET_POR_DEFECTO = 'olap.fact_projects'

interface StreamFrame {
  type?: string
  timestamp?: string
  anomaly_count?: number
}

export default function DataPlatformPage(): JSX.Element {
  const { t } = useAppLang()

  const toast = useToast()
  // 23-11-2026 (04 M10): sin preset fijo ('ops_delivery_mix'); se usa el elegido o, si no, el primero recibido.
  const [presetId, setPresetId] = useState('')
  const [streamLive, setStreamLive] = useState(false)
  const [streamSnapshot, setStreamSnapshot] = useState<StreamFrame | null>(null)

  const [phase3Tick, setPhase3Tick] = useState(0)
  const [datasetKey, setDatasetKey] = useState(DATASET_POR_DEFECTO)
  const [snapshotDiff, setSnapshotDiff] = useState<DiferenciaDeInstantaneasBi | null>(null)

  // 23-11-2026 (04 M6): las consultas ya no se tragan el error con `.catch`; avisa el onError global
  // y la pantalla pinta el estado de error de la que alimenta cada tarjeta.
  const { data: reportPresets = [], isError: presetsError, error: presetsErr, refetch: refetchPresets } = useQuery({
    queryKey: ['data-platform-report-presets'],
    // El interceptor ya deja la lista en `r.data` (envelope APIListResponse).
    queryFn: () => biIntelligenceApi.reportPresets().then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })
  const presetEfectivo = presetId || reportPresets[0]?.id || ''
  const { data: previewData, refetch: refetchPreview } = useQuery({
    queryKey: ['data-platform-preview', presetEfectivo],
    queryFn: () => biIntelligenceApi.previewPreset({ preset_id: presetEfectivo, limit: DATA_PREVIEW_ROWS }).then(r => r.data),
    enabled: !!presetEfectivo,
    staleTime: STALE_PREVIEW_MS,
  })
  const { data: deliveryOverview } = useQuery({
    queryKey: ['data-platform-delivery'],
    queryFn: () => biIntelligenceApi.deliveryOverview().then(r => r.data),
    staleTime: STALE_PREVIEW_MS,
  })
  const { data: phase3Lineage, refetch: refetchPhase3Lineage, isError: lineageError, error: lineageErr } = useQuery({
    queryKey: ['data-platform-lineage', phase3Tick],
    queryFn: () => biPlatformApi.lineage().then(r => r.data),
    staleTime: STALE_PREVIEW_MS,
  })
  const { data: phase3SnapshotItems = [], refetch: refetchPhase3Snapshots } = useQuery({
    queryKey: ['data-platform-snapshots', datasetKey, phase3Tick],
    queryFn: () => biPlatformApi.listSnapshots(datasetKey).then(r => r.data),
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
          } catch (_e) { /* accesorio: un fotograma mal formado del flujo en vivo se descarta; el siguiente llega solo */ }
        }
        ws.onclose = () => { if (!closed && streamLive) setTimeout(connect, WS_STREAM_RECONNECT_MS) }
      } catch (e) {
        // 23-11-2026: si no se consigue ni el ticket, se avisa y se apaga el flujo en vez de quedarse mudo.
        if (!closed) { toast.error(extractErr(e, t('dataplatform.error_streaming'))); setStreamLive(false) }
      }
    }
    connect()
    return () => { closed = true; if (ws) ws.close() }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- toast y t son estables en la práctica; reconectar por ellos reabriría el flujo
  }, [streamLive])

  const phase3LineageEdges = phase3Lineage?.edges ?? []

  async function handleCreateSnapshot() {
    try {
      await biPlatformApi.createSnapshot(datasetKey, {
        payload: { captured_at: new Date().toISOString(), source: 'data_platform_manual' },
      })
      setPhase3Tick(x => x + 1); await refetchPhase3Snapshots()
      toast.success(t('dataplatform.version_creada'))
    } catch (e) { toast.error(extractErr(e, t('dataplatform.error_crear_version'))) }
  }
  async function handleDiffLastSnapshots() {
    const items = phase3SnapshotItems
    if (items.length < 2) return
    const fromId = items[items.length - 2]?.id
    const toId = items[items.length - 1]?.id
    if (!fromId || !toId) return
    try { const res = await biPlatformApi.diffSnapshots(datasetKey, fromId, toId); setSnapshotDiff(res?.data || null) } catch (e) { toast.error(extractErr(e, t('dataplatform.error_comparar_versiones'))) }
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
              {presetsError && <EstadoDeError error={presetsErr} onReintentar={() => { void refetchPresets() }} />}
              <Select suelto placeholder={false} aria-label={t('dataplatform.presets')} value={presetEfectivo} onChange={e => setPresetId(e.target.value)} className="dpl-input">
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
              {lineageError && <EstadoDeError error={lineageErr} onReintentar={() => { void refetchPhase3Lineage() }} />}
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
