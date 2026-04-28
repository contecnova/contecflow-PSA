import { useMemo } from 'react'
import { hierarchy, treemap } from 'd3'

export default function TreemapChart({ data, width = 900, height = 380 }) {
  const nodes = useMemo(() => {
    const root = hierarchy(data || {
      name: 'Revenue',
      children: [
        { name: 'Cliente A', value: 320000 },
        { name: 'Cliente B', value: 240000 },
        { name: 'Cliente C', value: 180000 },
      ],
    })
      .sum((d) => d.value || 0)
      .sort((a, b) => b.value - a.value)

    treemap().size([width, height]).padding(3)(root)
    return root.leaves()
  }, [data, width, height])

  return (
    <svg width={width} height={height} role="img" aria-label="Treemap chart">
      {nodes.map((n) => (
        <g key={n.data.name}>
          <rect x={n.x0} y={n.y0} width={n.x1 - n.x0} height={n.y1 - n.y0} fill="#0f766e" opacity={0.85} rx={3} />
          <text x={n.x0 + 6} y={n.y0 + 16} fill="#f8fafc" fontSize="11">
            {n.data.name}
          </text>
        </g>
      ))}
    </svg>
  )
}
