import ReactECharts from 'echarts-for-react'
import { useChartTheme } from './useChartTheme'

export default function CandlestickChart({ data, width = 900, height = 380 }) {
  const { dark } = useChartTheme()
  const xAxis = data?.x || ['Lun', 'Mar', 'Mie', 'Jue', 'Vie']
  const candles = data?.candles || [
    [20, 34, 10, 38],
    [30, 42, 28, 46],
    [36, 31, 24, 40],
    [33, 45, 30, 48],
    [45, 39, 36, 50],
  ]

  const option = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: xAxis },
    yAxis: { scale: true },
    series: [{ type: 'candlestick', data: candles }],
  }

  return (
    <div role="img" aria-label="Candlestick chart">
      <ReactECharts option={option} theme={dark ? 'dark' : 'light'} style={{ width, height }} notMerge lazyUpdate />
    </div>
  )
}
