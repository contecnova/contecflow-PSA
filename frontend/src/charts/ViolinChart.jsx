import Plot from 'react-plotly.js'

export default function ViolinChart({ data, width = 900, height = 380 }) {
  const values = data?.values || [8, 10, 12, 12, 14, 18, 21, 22, 25, 28, 30]
  return (
    <Plot
      data={[{ type: 'violin', y: values, name: 'Carga', box: { visible: true }, meanline: { visible: true }, marker: { color: '#14b8a6' } }]}
      layout={{ width, height, margin: { t: 30, l: 40, r: 20, b: 40 }, paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#e5e7eb' } }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: '100%', height }}
      useResizeHandler
    />
  )
}
