/**
 * SurfaceChart — Plotly 3D surface chart.
 * Supports dark mode via useChartTheme.
 */
import Plot from 'react-plotly.js'
import { useChartTheme } from './useChartTheme'

function buildDefaultZ() {
  const z = []
  for (let i = 0; i < 20; i++) {
    const row = []
    for (let j = 0; j < 20; j++) {
      row.push(Math.sin(i * 0.4) * Math.cos(j * 0.4) * 50 + Math.random() * 5)
    }
    z.push(row)
  }
  return z
}

export default function SurfaceChart({ data, width = 900, height = 420 }) {
  const { tokens, dark } = useChartTheme()
  const z = data?.z || buildDefaultZ()
  const x = data?.x || Array.from({ length: z[0]?.length || 20 }, (_, i) => i)
  const y = data?.y || Array.from({ length: z.length }, (_, i) => i)

  return (
    <div role="img" aria-label="3D surface chart">
      <Plot
        data={[
          {
            type: 'surface',
            x,
            y,
            z,
            colorscale: dark ? 'Cividis' : 'Viridis',
            showscale: true,
            opacity: 0.92,
            contours: {
              z: { show: true, usecolormap: true, highlightcolor: tokens.accent, project: { z: false } },
            },
          },
        ]}
        layout={{
          width,
          height,
          margin: { t: 30, l: 0, r: 0, b: 0 },
          scene: {
            xaxis: { title: data?.xlabel || 'X', color: tokens.text2, gridcolor: tokens.text3 },
            yaxis: { title: data?.ylabel || 'Y', color: tokens.text2, gridcolor: tokens.text3 },
            zaxis: { title: data?.zlabel || 'Z', color: tokens.text2, gridcolor: tokens.text3 },
            bgcolor: 'transparent',
          },
          paper_bgcolor: 'transparent',
          plot_bgcolor: 'transparent',
          font: { color: tokens.text1, family: 'system-ui, sans-serif', size: 11 },
        }}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: '100%', height }}
        useResizeHandler
      />
    </div>
  )
}
