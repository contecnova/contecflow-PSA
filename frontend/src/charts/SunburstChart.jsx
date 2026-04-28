import { useMemo } from 'react'
import { hierarchy, partition, arc } from 'd3'

export default function SunburstChart({ data, width = 900, height = 380 }) {
  const radius = Math.min(width, height) / 2 - 8
  const chartData = useMemo(() => {
    const root = hierarchy(data || {
      name: 'Portfolio',
      children: [
        { name: 'Delivery', children: [{ name: 'Alpha', value: 70 }, { name: 'Beta', value: 45 }] },
        { name: 'Support', children: [{ name: 'Gamma', value: 32 }, { name: 'Delta', value: 18 }] },
      ],
    }).sum((d) => d.value || 0)

    return partition().size([2 * Math.PI, radius])(root).descendants().filter((d) => d.depth > 0)
  }, [data, radius])

  const arcPath = arc()
    .startAngle((d) => d.x0)
    .endAngle((d) => d.x1)
    .innerRadius((d) => d.y0)
    .outerRadius((d) => d.y1)

  return (
    <svg width={width} height={height} role="img" aria-label="Sunburst chart">
      <g transform={`translate(${width / 2}, ${height / 2})`}>
        {chartData.map((d, i) => (
          <path key={`${d.data.name}-${i}`} d={arcPath(d)} fill={`hsl(${(i * 47) % 360},70%,45%)`} opacity={0.86} />
        ))}
      </g>
    </svg>
  )
}
