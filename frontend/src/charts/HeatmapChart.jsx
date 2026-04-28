import ReactECharts from 'echarts-for-react'

export default function HeatmapChart({ data, width = 900, height = 380 }) {
  const x = data?.x || ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun']
  const y = data?.y || ['Alpha', 'Beta', 'Gamma', 'Delta']
  const values = data?.values || y.flatMap((_, yi) => x.map((_, xi) => [xi, yi, Math.round(Math.random() * 100)]))

  const option = {
    tooltip: {},
    xAxis: { type: 'category', data: x },
    yAxis: { type: 'category', data: y },
    visualMap: { min: 0, max: 100, calculable: true, orient: 'horizontal', left: 'center', bottom: 0 },
    grid: { bottom: 60 },
    series: [{ type: 'heatmap', data: values, label: { show: true, color: '#111827' } }],
  }

  return <ReactECharts option={option} style={{ width, height }} notMerge lazyUpdate />
}
