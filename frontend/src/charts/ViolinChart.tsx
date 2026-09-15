import Plot from './PlotlyCustom'
import { useChartTheme } from './useChartTheme'

export interface ViolinChartData {
  values?: number[]
}

export interface ViolinChartProps {
  data?: ViolinChartData
  width?: number
  height?: number
}

export default function ViolinChart({ data, width = 900, height = 380 }: ViolinChartProps) {
  const { tokens } = useChartTheme()
  const values = data?.values || [8, 10, 12, 12, 14, 18, 21, 22, 25, 28, 30]
  return (
    <div role="img" aria-label="Violin chart">
      <Plot
        data={[{ type: 'violin', y: values, name: 'Carga', box: { visible: true }, meanline: { visible: true }, marker: { color: tokens.success } }]}
        layout={{ width, height, margin: { t: 30, l: 40, r: 20, b: 40 }, paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: tokens.text1 } }}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: '100%', height }}
        useResizeHandler
      />
    </div>
  )
}
