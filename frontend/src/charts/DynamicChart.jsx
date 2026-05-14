import { Suspense, lazy, useMemo } from 'react'

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

const COMPONENT_MAP = {
  sankey: SankeyChart,
  treemap: TreemapChart,
  sunburst: SunburstChart,
  dendrogram: DendrogramChart,
  gauge: GaugeChart,
  heatmap: HeatmapChart,
  funnel: FunnelChart,
  candlestick: CandlestickChart,
  bar3d: Chart3DBar,
  box: BoxPlotChart,
  violin: ViolinChart,
  scatter3d: Scatter3DChart,
  network: NetworkChart,
  surface: SurfaceChart,
}

export default function DynamicChart({ type = 'treemap', data, config = {} }) {
  const width = config.width || 900
  const height = config.height || 380

  const ChartComponent = useMemo(() => COMPONENT_MAP[type] || TreemapChart, [type])
  return (
    <Suspense fallback={<div style={{ width, height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-2)', fontSize: 'var(--text-sm)' }}>Cargando gráfico…</div>}>
      <ChartComponent data={data} width={width} height={height} config={config} />
    </Suspense>
  )
}
