/**
 * DataPlatformPage — Plataforma de datos: ETL, conectores,
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
import { biIntelligenceApi, biPlatformApi, unwrapList, wsApi, apiWsUrl } from '../services/api'
import BiEtlPanel from '../components/bi/BiEtlPanel'
import BiO365Panel from '../components/bi/BiO365Panel'
import { localeActivo } from '../utils/helpers'

interface ReportPresetItem {
  id: string
  name: string
}


interface LineageResponse {
  edges?: unknown[]
}

interface SnapshotItem {
  id: string | number
}

interface SnapshotDiff {
  change_count?: number
}

interface StreamFrame {
  type?: string
  timestamp?: string
  anomaly_count?: number
}

const S = {
  card:        { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14, overflow: 'hidden' },
  cardPad:     { padding: '20px 24px' },
  sectionTitle:{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.09em', margin: 0 },
  input:       { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', color: 'var(--text-1)', borderRadius: 8, padding: '9px 13px', fontSize: 'var(--text-base)', fontFamily: 'inherit', outline: 'none', width: '100%' },
  btnSecondary:{ padding: '7px 16px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 'var(--text-sm)', fontFamily: 'inherit' },
  btnAccentOutline: (c: string = COLOR.accent) => ({ padding: '7px 14px', borderRadius: 8, border: `1px solid ${c}`, background: alpha(c, '18'), color: c, cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 600, fontFamily: 'inherit' }),
}

const getLocale = (lang?: string) => localeActivo(lang)

export default function DataPlatformPage(): JSX.Element {
  const { t } = useAppLang()
  const { lang } = useAppLang()
  const isMobile = useMediaQuery('(max-width: 900px)')

  const [presetId, setPresetId] = useState('ops_delivery_mix')
  const [streamLive, setStreamLive] = useState(false)
  const [streamSnapshot, setStreamSnapshot] = useState<StreamFrame | null>(null)

  const [phase3Tick, setPhase3Tick] = useState(0)
  const [datasetKey, setDatasetKey] = useState('olap.fact_projects')
  const [snapshotDiff, setSnapshotDiff] = useState<SnapshotDiff | null>(null)

  const { data: reportPresetsRaw } = useQuery({
    queryKey: ['data-platform-report-presets'],
    // El interceptor ya deja la lista en `r.data` (envelope APIListResponse).
    queryFn: () => biIntelligenceApi.reportPresets().then(r => r.data as ReportPresetItem[]).catch(() => [] as ReportPresetItem[]),
    staleTime: 60_000,
  })
  const reportPresets = unwrapList(reportPresetsRaw) as ReportPresetItem[]
  const { data: previewData, refetch: refetchPreview } = useQuery({
    queryKey: ['data-platform-preview', presetId],
    queryFn: () => biIntelligenceApi.previewPreset({ preset_id: presetId, limit: 20 }).then(r => r.data).catch(() => null),
    staleTime: 20_000,
  })
  const { data: deliveryOverview } = useQuery({
    queryKey: ['data-platform-delivery'],
    queryFn: () => biIntelligenceApi.deliveryOverview().then(r => r.data).catch(() => null),
    staleTime: 20_000,
  })
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
        ws.onclose = () => { if (!closed && streamLive) setTimeout(connect, 2000) }
      } catch (_e) { /* keep UI responsive */ }
    }
    connect()
    return () => { closed = true; if (ws) ws.close() }
  }, [streamLive])

  const phase3LineageEdges = phase3Lineage?.edges || []
  const phase3SnapshotItems = unwrapList(phase3SnapshotsRaw) as SnapshotItem[]

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
    <PageShell style={isMobile ? { paddingLeft: 14, paddingRight: 14 } : undefined}>
      <PageHeader
        icon={<Database size={18} />}
        title={t('dataplatform.titulo')}
        subtitle={t('dataplatform.subtitulo')}
        showListExport={false}
      />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <BiEtlPanel />
        <BiO365Panel />

        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fit, minmax(300px, 1fr))', gap: 14 }}>
          <div style={S.card}>
            <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>{t('dataplatform.presets')}</div></div>
            <div style={{ ...S.cardPad, display: 'grid', gap: 10 }}>
              <select aria-label={t('dataplatform.presets')} value={presetId} onChange={e => setPresetId(e.target.value)} style={S.input}>
                {reportPresets.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <button onClick={() => refetchPreview()} style={S.btnAccentOutline()}>{t('dataplatform.previsualizar')}</button>
              <div className="u-text3-xs">{t('dataplatform.filas_preview', { n: previewData?.count || 0 })}</div>
              <div className="u-text3-xs">
                {t('dataplatform.envios', { activos: deliveryOverview?.active ?? 0, errores: deliveryOverview?.errored ?? 0 })}
              </div>
            </div>
          </div>
          <div style={S.card}>
            <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>{t('dataplatform.streaming')}</div></div>
            <div style={{ ...S.cardPad, display: 'grid', gap: 10 }}>
              <button onClick={() => setStreamLive(v => !v)}
                style={{ ...S.btnAccentOutline(streamLive ? COLOR.success : 'var(--surface-5)'), color: streamLive ? COLOR.success : 'var(--text-2)' }}>
                {t(streamLive ? 'dataplatform.streaming_activo' : 'dataplatform.activar_streaming')}
              </button>
              <div className="u-text3-xs">
                {streamSnapshot?.timestamp
                  ? t('dataplatform.instantanea', { hora: new Date(streamSnapshot.timestamp).toLocaleTimeString(getLocale(lang)), n: streamSnapshot.anomaly_count ?? 0 })
                  : t('dataplatform.sin_instantanea')}
              </div>
            </div>
          </div>
          <div style={S.card}>
            <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)' }}><div style={S.sectionTitle}>{t('dataplatform.linaje')}</div></div>
            <div style={{ ...S.cardPad, display: 'grid', gap: 8 }}>
              <div className="u-text2-sm">
                {t('dataplatform.aristas_y_versiones', { aristas: phase3LineageEdges.length, versiones: phase3SnapshotItems.length })}
              </div>
              <input aria-label={t('dataplatform.dataset')} value={datasetKey} onChange={e => setDatasetKey(e.target.value)} placeholder={t('dataplatform.dataset')} style={S.input} />
              <div className="u-wrap-8">
                <button onClick={handleCreateSnapshot} style={S.btnAccentOutline()}>{t('dataplatform.crear_version')}</button>
                <button onClick={handleDiffLastSnapshots} style={S.btnSecondary}>{t('dataplatform.diff_ultimos_2')}</button>
                <button onClick={() => refetchPhase3Lineage()} style={S.btnSecondary}>{t('dataplatform.refrescar')}</button>
              </div>
              {snapshotDiff && <div className="u-text3-xs">{t('dataplatform.cambios', { n: snapshotDiff?.change_count ?? 0 })}</div>}
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  )
}
