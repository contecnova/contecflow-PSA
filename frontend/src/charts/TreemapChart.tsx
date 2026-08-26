import { useMemo } from 'react'
// TODO type: d3 ESM types are partial.
import { hierarchy, treemap } from 'd3'
import { useChartTheme } from './useChartTheme'

export interface TreemapNode {
  name: string
  value?: number
  children?: TreemapNode[]
}

export interface TreemapChartProps {
  data?: TreemapNode
  width?: number
  height?: number
}

export default function TreemapChart({ data, width = 900, height = 380 }: TreemapChartProps) {
  const { tokens } = useChartTheme()
  const nodes = useMemo(() => {
    const root = hierarchy<TreemapNode>(data || {
      name: 'Revenue',
      children: [
        { name: 'Cliente A', value: 320000 },
        { name: 'Cliente B', value: 240000 },
        { name: 'Cliente C', value: 180000 },
      ],
    })
      .sum((d) => d.value || 0)
      .sort((a, b) => (b.value || 0) - (a.value || 0))

     
    ;(treemap() as any).size([width, height]).padding(3)(root)
    return root.leaves()
  }, [data, width, height])

  return (
    <svg width={width} height={height} role="img" aria-label="Treemap chart">
      {nodes.map((n) => {
         
        const tn = n as any
        return (
          <g key={n.data.name}>
            <rect x={tn.x0} y={tn.y0} width={tn.x1 - tn.x0} height={tn.y1 - tn.y0} fill={tokens.accent} opacity={0.85} rx={3} />
            <text x={tn.x0 + 6} y={tn.y0 + 16} fill={tokens.text1} fontSize="11">
              {n.data.name}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
