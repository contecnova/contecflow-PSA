import { useMemo } from 'react'
// TODO type: d3 ESM types are partial.
import { hierarchy, partition, arc } from 'd3'
import { useChartTheme } from './useChartTheme'

export interface SunburstNode {
  name: string
  value?: number
  children?: SunburstNode[]
}

export interface SunburstChartProps {
  data?: SunburstNode
  width?: number
  height?: number
}

export default function SunburstChart({ data, width = 900, height = 380 }: SunburstChartProps) {
  useChartTheme()
  const radius = Math.min(width, height) / 2 - 8
  const chartData = useMemo(() => {
    const root = hierarchy<SunburstNode>(data || {
      name: 'Portfolio',
      children: [
        { name: 'Delivery', children: [{ name: 'Alpha', value: 70 }, { name: 'Beta', value: 45 }] },
        { name: 'Support', children: [{ name: 'Gamma', value: 32 }, { name: 'Delta', value: 18 }] },
      ],
    }).sum((d) => d.value || 0)

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return (partition() as any).size([2 * Math.PI, radius])(root).descendants().filter((d: any) => d.depth > 0)
  }, [data, radius])

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const arcPath = (arc() as any)
    .startAngle((d: any) => d.x0)
    .endAngle((d: any) => d.x1)
    .innerRadius((d: any) => d.y0)
    .outerRadius((d: any) => d.y1)

  return (
    <svg width={width} height={height} role="img" aria-label="Sunburst chart">
      <g transform={`translate(${width / 2}, ${height / 2})`}>
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        {chartData.map((d: any, i: number) => (
          <path key={`${d.data.name}-${i}`} d={arcPath(d)} fill={`hsl(${(i * 47) % 360},70%,45%)`} opacity={0.86} />
        ))}
      </g>
    </svg>
  )
}
