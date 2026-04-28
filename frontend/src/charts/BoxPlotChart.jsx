import Plot from 'react-plotly.js'

export default function BoxPlotChart({ data, width = 900, height = 380 }) {
  const points = data?.points || [12, 16, 18, 21, 21, 24, 28, 34, 37, 42]
  return (
    <Plot
      data={[{ type: 'box', y: points, name: 'Duracion', marker: { color: '#0284c7' } }]}
      layout={{ width, height, margin: { t: 30, l: 40, r: 20, b: 40 }, paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#e5e7eb' } }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: '100%', height }}
      useResizeHandler
    />
  )
}
