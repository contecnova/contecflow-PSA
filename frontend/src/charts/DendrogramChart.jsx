import { useMemo } from 'react'
import { hierarchy, cluster } from 'd3'
import { useChartTheme } from './useChartTheme'

export default function DendrogramChart({ data, width = 900, height = 380 }) {
  const { tokens } = useChartTheme()
  const { links, nodes } = useMemo(() => {
    const root = hierarchy(data || {
      name: 'CMDB',
      children: [
        { name: 'Apps', children: [{ name: 'CRM' }, { name: 'ERP' }] },
        { name: 'Infra', children: [{ name: 'DB' }, { name: 'K8s' }, { name: 'Network' }] },
      ],
    })
    cluster().size([height - 20, width - 160])(root)
    return { links: root.links(), nodes: root.descendants() }
  }, [data, width, height])

  return (
    <svg width={width} height={height} role="img" aria-label="Dendrogram chart">
      <g transform="translate(80,10)">
        {links.map((l, i) => (
          <path key={i} d={`M${l.source.y},${l.source.x}L${l.target.y},${l.target.x}`} stroke={tokens.text3} fill="none" />
        ))}
        {nodes.map((n, i) => (
          <g key={i} transform={`translate(${n.y},${n.x})`}>
            <circle r={4} fill={tokens.info} />
            <text x={8} y={3} fontSize="11" fill={tokens.text1}>{n.data.name}</text>
          </g>
        ))}
      </g>
    </svg>
  )
}
