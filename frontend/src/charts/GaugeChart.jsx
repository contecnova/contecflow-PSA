import ReactECharts from 'echarts-for-react'

export default function GaugeChart({ data, width = 900, height = 380 }) {
  const value = Number(data?.value ?? 72)
  const option = {
    series: [{
      type: 'gauge',
      min: 0,
      max: 100,
      axisLine: { lineStyle: { width: 26 } },
      detail: { formatter: '{value}%' },
      data: [{ value, name: data?.name || 'Utilizacion' }],
    }],
  }
  return <ReactECharts option={option} style={{ width, height }} notMerge lazyUpdate />
}
