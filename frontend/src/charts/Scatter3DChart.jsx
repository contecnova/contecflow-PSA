import Plot from 'react-plotly.js'

export default function Scatter3DChart({ data, width = 900, height = 380 }) {
  const x = data?.x || [1, 2, 3, 4, 5]
  const y = data?.y || [2, 1, 4, 3, 5]
  const z = data?.z || [100, 160, 130, 190, 240]

  return (
    <Plot
      data={[{ type: 'scatter3d', mode: 'markers', x, y, z, marker: { size: 6, color: z, colorscale: 'Viridis' } }]}
      layout={{ width, height, margin: { t: 20, l: 0, r: 0, b: 0 }, scene: { xaxis: { title: 'Coste' }, yaxis: { title: 'Riesgo' }, zaxis: { title: 'Revenue' } }, paper_bgcolor: 'transparent', font: { color: '#e5e7eb' } }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: '100%', height }}
      useResizeHandler
    />
  )
}
