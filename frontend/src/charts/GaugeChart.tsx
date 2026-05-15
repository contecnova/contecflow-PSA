import ReactECharts from 'echarts-for-react'
import { useChartTheme } from './useChartTheme'

export interface GaugeChartData {
  value?: number | string
  name?: string
}

export interface GaugeChartProps {
  data?: GaugeChartData
  width?: number
  height?: number
}

export default function GaugeChart({ data, width = 900, height = 380 }: GaugeChartProps) {
  const { dark } = useChartTheme()
  const value = Number(data?.value ?? 72)
  const option = {
    backgroundColor: 'transparent',
    series: [{
      type: 'gauge',
      min: 0,
      max: 100,
      axisLine: { lineStyle: { width: 26 } },
      detail: { formatter: '{value}%' },
      data: [{ value, name: data?.name || 'Utilizacion' }],
    }],
  }
  return (
    <div role="img" aria-label={data?.name ? `Gauge chart: ${data.name}` : 'Gauge chart'}>
      <ReactECharts option={option} theme={dark ? 'dark' : 'light'} style={{ width, height }} notMerge lazyUpdate />
    </div>
  )
}
