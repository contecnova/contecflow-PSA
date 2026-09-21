import { Suspense, lazy, useMemo, ComponentType } from 'react'
import { useAppLang } from '../i18n/AppLangContext'

// Lazy-load each chart implementation so the heavy chart libraries
// (plotly.js, echarts) are split into per-type bundles and only fetched
// when that specific visualization is rendered.
const SankeyChart      = lazy(() => import('./SankeyChart'))
const TreemapChart     = lazy(() => import('./TreemapChart'))
const SunburstChart    = lazy(() => import('./SunburstChart'))
const DendrogramChart  = lazy(() => import('./DendrogramChart'))
const GaugeChart       = lazy(() => import('./GaugeChart'))
const HeatmapChart     = lazy(() => import('./HeatmapChart'))
const FunnelChart      = lazy(() => import('./FunnelChart'))
const CandlestickChart = lazy(() => import('./CandlestickChart'))
const Chart3DBar       = lazy(() => import('./Chart3DBar'))
const BoxPlotChart     = lazy(() => import('./BoxPlotChart'))
const ViolinChart      = lazy(() => import('./ViolinChart'))
const Scatter3DChart   = lazy(() => import('./Scatter3DChart'))
const NetworkChart     = lazy(() => import('./NetworkChart'))
const SurfaceChart     = lazy(() => import('./SurfaceChart'))

export type ChartType =
  | 'sankey'
  | 'treemap'
  | 'sunburst'
  | 'dendrogram'
  | 'gauge'
  | 'heatmap'
  | 'funnel'
  | 'candlestick'
  | 'bar3d'
  | 'box'
  | 'violin'
  | 'scatter3d'
  | 'network'
  | 'surface'

// TODO type: individual chart prop shapes vary per type — keep loose here.
type AnyChartProps = {
  data?: unknown
  width?: number
  height?: number
  config?: Record<string, unknown>
}

const COMPONENT_MAP: Record<ChartType, ComponentType<AnyChartProps>> = {
  sankey: SankeyChart as unknown as ComponentType<AnyChartProps>,
  treemap: TreemapChart as unknown as ComponentType<AnyChartProps>,
  sunburst: SunburstChart as unknown as ComponentType<AnyChartProps>,
  dendrogram: DendrogramChart as unknown as ComponentType<AnyChartProps>,
  gauge: GaugeChart as unknown as ComponentType<AnyChartProps>,
  heatmap: HeatmapChart as unknown as ComponentType<AnyChartProps>,
  funnel: FunnelChart as unknown as ComponentType<AnyChartProps>,
  candlestick: CandlestickChart as unknown as ComponentType<AnyChartProps>,
  bar3d: Chart3DBar as unknown as ComponentType<AnyChartProps>,
  box: BoxPlotChart as unknown as ComponentType<AnyChartProps>,
  violin: ViolinChart as unknown as ComponentType<AnyChartProps>,
  scatter3d: Scatter3DChart as unknown as ComponentType<AnyChartProps>,
  network: NetworkChart as unknown as ComponentType<AnyChartProps>,
  surface: SurfaceChart as unknown as ComponentType<AnyChartProps>,
}

export interface DynamicChartConfig extends Record<string, unknown> {
  width?: number
  height?: number
}

export interface DynamicChartProps {
  type?: ChartType
  // TODO type: data shape is type-dependent (see individual chart components).
  data?: unknown
  config?: DynamicChartConfig
}

export default function DynamicChart({ type = 'treemap', data, config = {} }: DynamicChartProps) {
  const { t } = useAppLang()
  const width = (config.width as number | undefined) || 900
  const height = (config.height as number | undefined) || 380

  const ChartComponent = useMemo(() => COMPONENT_MAP[type] || (TreemapChart as unknown as ComponentType<AnyChartProps>), [type])
  return (
    <Suspense fallback={<div style={{ width, height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-2)', fontSize: 'var(--text-sm)' }}>{t('dynamicchart.cargando_grafico')}</div>}>
      <ChartComponent data={data} width={width} height={height} config={config} />
    </Suspense>
  )
}
