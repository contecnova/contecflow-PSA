import { useMemo } from 'react'
// TODO type: d3-sankey types may not be installed.
import { sankey as d3Sankey, sankeyLinkHorizontal } from 'd3-sankey'
import { useChartTheme } from './useChartTheme'

export interface SankeyNodeInput {
  id: string
}

export interface SankeyLinkInput {
  source: string
  target: string
  value: number
}

export interface SankeyChartData {
  nodes?: SankeyNodeInput[]
  links?: SankeyLinkInput[]
}

export interface SankeyChartProps {
  data?: SankeyChartData
  width?: number
  height?: number
}

// d3-sankey augments nodes/links with positional fields at runtime.
interface SankeyNodeComputed extends SankeyNodeInput {
  x0: number
  x1: number
  y0: number
  y1: number
}

interface SankeyLinkComputed {
  width: number
  source: SankeyNodeComputed
  target: SankeyNodeComputed
  value: number
}

export default function SankeyChart({ data, width = 900, height = 380 }: SankeyChartProps) {
  const { tokens } = useChartTheme()
  const graph = useMemo(() => {
    const nodes = (data?.nodes || [
      { id: 'Leads' },
      { id: 'Propuestas' },
      { id: 'Ganados' },
      { id: 'Perdidos' },
    ]).map((n) => ({ ...n }))
    const links = (data?.links || [
      { source: 'Leads', target: 'Propuestas', value: 120 },
      { source: 'Propuestas', target: 'Ganados', value: 65 },
      { source: 'Propuestas', target: 'Perdidos', value: 55 },
    ]).map((l) => ({ ...l }))

     
    return (d3Sankey() as any)
      .nodeId((d: SankeyNodeInput) => d.id)
      .nodeWidth(12)
      .nodePadding(22)
      .extent([[1, 1], [width - 1, height - 8]])({ nodes, links }) as {
        nodes: SankeyNodeComputed[]
        links: SankeyLinkComputed[]
      }
  }, [data, width, height])

  return (
    <svg width={width} height={height} role="img" aria-label="Sankey chart">
      <g fill="none" strokeOpacity="0.38">
        {graph.links.map((link, i) => (
          <path
            key={i}
             
            d={(sankeyLinkHorizontal() as any)(link)}
            stroke={tokens.info}
            strokeWidth={Math.max(1, link.width)}
          />
        ))}
      </g>
      <g>
        {graph.nodes.map((node) => (
          <g key={node.id}>
            <rect
              x={node.x0}
              y={node.y0}
              width={node.x1 - node.x0}
              height={Math.max(1, node.y1 - node.y0)}
              fill={tokens.accent}
              opacity={0.8}
              rx={2}
            />
            <text x={node.x1 + 6} y={(node.y0 + node.y1) / 2} dominantBaseline="middle" fill={tokens.text1} fontSize="11">
              {node.id}
            </text>
          </g>
        ))}
      </g>
    </svg>
  )
}
