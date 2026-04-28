import ReactECharts from 'echarts-for-react'

export default function FunnelChart({ data, width = 900, height = 380 }) {
  const option = {
    tooltip: { trigger: 'item', formatter: '{b}: {c}%' },
    series: [{
      type: 'funnel',
      data: data || [
        { value: 100, name: 'Leads' },
        { value: 72, name: 'Calificados' },
        { value: 43, name: 'Propuesta' },
        { value: 25, name: 'Negociacion' },
        { value: 13, name: 'Cierre' },
      ],
    }],
  }

  return <ReactECharts option={option} style={{ width, height }} notMerge lazyUpdate />
}
