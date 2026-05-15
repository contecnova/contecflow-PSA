import ReactECharts from 'echarts-for-react'
import { useChartTheme } from './useChartTheme'

export type HeatmapCell = [number, number, number]

export interface HeatmapChartData {
  x?: string[]
  y?: string[]
  values?: HeatmapCell[]
}

export interface HeatmapChartProps {
  data?: HeatmapChartData
  width?: number
  height?: number
}

export default function HeatmapChart({ data, width = 900, height = 380 }: HeatmapChartProps) {
  const { dark } = useChartTheme()
  const x = data?.x || ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun']
  const y = data?.y || ['Alpha', 'Beta', 'Gamma', 'Delta']
  const values: HeatmapCell[] = data?.values || y.flatMap((_, yi) => x.map((_, xi): HeatmapCell => [xi, yi, Math.round(Math.random() * 100)]))

  const option = {
    backgroundColor: 'transparent',
    tooltip: {},
    xAxis: { type: 'category', data: x },
    yAxis: { type: 'category', data: y },
    visualMap: { min: 0, max: 100, calculable: true, orient: 'horizontal', left: 'center', bottom: 0 },
    grid: { bottom: 60 },
    series: [{ type: 'heatmap', data: values, label: { show: true } }],
  }

  return (
    <div role="img" aria-label="Heatmap chart">
      <ReactECharts option={option} theme={dark ? 'dark' : 'light'} style={{ width, height }} notMerge lazyUpdate />
    </div>
  )
}
