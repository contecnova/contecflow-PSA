import ReactECharts from 'echarts-for-react'

export default function Chart3DBar({ data, width = 900, height = 380 }) {
  const categories = data?.categories || ['Q1', 'Q2', 'Q3', 'Q4']
  const values = data?.values || [120, 180, 145, 220]

  const option = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: categories },
    yAxis: { type: 'value' },
    series: [{
      type: 'bar',
      data: values,
      itemStyle: {
        borderRadius: [6, 6, 0, 0],
        shadowBlur: 12,
        shadowColor: 'rgba(14,165,233,.45)',
      },
    }],
  }

  return <ReactECharts option={option} style={{ width, height }} notMerge lazyUpdate />
}
