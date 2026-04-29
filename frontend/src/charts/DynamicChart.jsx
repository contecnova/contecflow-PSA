import { useMemo } from 'react'
import {
  SankeyChart,
  TreemapChart,
  SunburstChart,
  DendrogramChart,
  GaugeChart,
  HeatmapChart,
  FunnelChart,
  CandlestickChart,
  Chart3DBar,
  BoxPlotChart,
  ViolinChart,
  Scatter3DChart,
  NetworkChart,
  SurfaceChart,
} from './index'

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
  return <ChartComponent data={data} width={width} height={height} config={config} />
}
