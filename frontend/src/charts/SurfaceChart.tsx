/**
 * SurfaceChart — Plotly 3D surface chart.
 * Supports dark mode via useChartTheme.
 */
import Plot from 'react-plotly.js'
import { useChartTheme } from './useChartTheme'

export interface SurfaceChartData {
  x?: number[]
  y?: number[]
  z?: number[][]
  xlabel?: string
  ylabel?: string
  zlabel?: string
}

export interface SurfaceChartProps {
  data?: SurfaceChartData
  width?: number
  height?: number
}

function buildDefaultZ(): number[][] {
  const z: number[][] = []
  for (let i = 0; i < 20; i++) {
    const row: number[] = []
    for (let j = 0; j < 20; j++) {
      row.push(Math.sin(i * 0.4) * Math.cos(j * 0.4) * 50 + Math.random() * 5)
    }
    z.push(row)
  }
  return z
}

export default function SurfaceChart({ data, width = 900, height = 420 }: SurfaceChartProps) {
  const { tokens, dark } = useChartTheme()
  const z = data?.z || buildDefaultZ()
  const x = data?.x || Array.from({ length: z[0]?.length || 20 }, (_, i) => i)
  const y = data?.y || Array.from({ length: z.length }, (_, i) => i)

  return (
    <div role="img" aria-label="3D surface chart">
      <Plot
        data={[
          {
            type: 'surface' as const,
            x,
            y,
            z,
            colorscale: dark ? 'Cividis' : 'Viridis',
            showscale: true,
            opacity: 0.92,
            // @types/plotly.js modela `contours` sólo para trazas contour (2D);
            // para una traza `surface` la forma correcta lleva sub-objetos x/y/z.
            // El código es válido en Plotly, los tipos están incompletos: se
            // acota el cast a esta propiedad en vez de aflojar la traza entera.
            contours: {
              z: { show: true, usecolormap: true, highlightcolor: tokens.accent, project: { z: false } },
            } as unknown as never,
          },
        ]}
        layout={{
          width,
          height,
          margin: { t: 30, l: 0, r: 0, b: 0 },
          scene: {
            xaxis: { title: { text: data?.xlabel || 'X' }, color: tokens.text2, gridcolor: tokens.text3 },
            yaxis: { title: { text: data?.ylabel || 'Y' }, color: tokens.text2, gridcolor: tokens.text3 },
            zaxis: { title: { text: data?.zlabel || 'Z' }, color: tokens.text2, gridcolor: tokens.text3 },
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
