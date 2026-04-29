import ReactECharts from 'echarts-for-react'
import { useChartTheme } from './useChartTheme'

export default function FunnelChart({ data, width = 900, height = 380 }) {
  const { dark } = useChartTheme()
  const option = {
    backgroundColor: 'transparent',
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

  return (
    <div role="img" aria-label="Funnel chart">
      <ReactECharts option={option} theme={dark ? 'dark' : 'light'} style={{ width, height }} notMerge lazyUpdate />
    </div>
  )
}
