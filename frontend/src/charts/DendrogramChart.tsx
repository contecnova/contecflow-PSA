import { useMemo } from 'react'
// TODO type: d3 imports — d3 ESM types are partial
import { hierarchy, cluster } from 'd3'
import { useChartTheme } from './useChartTheme'

export interface DendrogramNode {
  name: string
  children?: DendrogramNode[]
}

export interface DendrogramChartProps {
  data?: DendrogramNode
  width?: number
  height?: number
}

export default function DendrogramChart({ data, width = 900, height = 380 }: DendrogramChartProps) {
  const { tokens } = useChartTheme()
  const { links, nodes } = useMemo(() => {
    const root = hierarchy<DendrogramNode>(data || {
      name: 'CMDB',
      children: [
        { name: 'Apps', children: [{ name: 'CRM' }, { name: 'ERP' }] },
        { name: 'Infra', children: [{ name: 'DB' }, { name: 'K8s' }, { name: 'Network' }] },
      ],
    })
    cluster<DendrogramNode>().size([height - 20, width - 160])(root)
    return { links: root.links(), nodes: root.descendants() }
  }, [data, width, height])

  return (
    <svg width={width} height={height} role="img" aria-label="Dendrogram chart">
      <g transform="translate(80,10)">
        {links.map((l, i) => {
          const s = l.source as unknown as { x: number; y: number }
          const t = l.target as unknown as { x: number; y: number }
          return (
            <path key={i} d={`M${s.y},${s.x}L${t.y},${t.x}`} stroke={tokens.text3} fill="none" />
          )
        })}
        {nodes.map((n, i) => {
          const pos = n as unknown as { x: number; y: number }
          return (
            <g key={i} transform={`translate(${pos.y},${pos.x})`}>
              <circle r={4} fill={tokens.info} />
              <text x={8} y={3} fontSize="11" fill={tokens.text1}>{n.data.name}</text>
            </g>
          )
        })}
      </g>
    </svg>
  )
}
