import Plot from 'react-plotly.js'
import { useChartTheme } from './useChartTheme'

export interface BoxPlotData {
  points?: number[]
}

export interface BoxPlotChartProps {
  data?: BoxPlotData
  width?: number
  height?: number
}

export default function BoxPlotChart({ data, width = 900, height = 380 }: BoxPlotChartProps) {
  const { tokens } = useChartTheme()
  const points = data?.points || [12, 16, 18, 21, 21, 24, 28, 34, 37, 42]
  return (
    <div role="img" aria-label="Box plot chart">
      <Plot
        data={[{ type: 'box', y: points, name: 'Duracion', marker: { color: tokens.info } }]}
        layout={{ width, height, margin: { t: 30, l: 40, r: 20, b: 40 }, paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: tokens.text1 } }}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: '100%', height }}
        useResizeHandler
      />
    </div>
  )
}
